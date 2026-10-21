import io
import openpyxl
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from academics.models import SchoolClass, Student, Teacher
from accounts.models import User
from audit.models import AuditLog
from guardians.models import Guardian, StudentGuardian
from organizations.models import Organization, OrganizationMember, SchoolOrganization
from schools.models import School


def create_excel_file(headers, rows, sheet_name="Sheet1"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


class ImportersTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.principal = User.objects.create_user(
            username="apex_principal",
            email="principal@apex.edu",
            password="StrongPassword@123!",
            role="admin",
        )
        self.org = Organization.objects.create(name="Apex Group", code="APEX", owner=self.principal)
        self.school = School.objects.create(name="Apex International", code="APEX01", principal=self.principal)
        self.school_org = SchoolOrganization.objects.create(
            organization=self.org,
            school=self.school,
            status="active",
        )
        OrganizationMember.objects.create(
            organization=self.org,
            user=self.principal,
            role="owner",
        )

        # Another school for tenant isolation and multi-school tests
        self.principal_other = User.objects.create_user(
            username="other_principal",
            email="principal@other.edu",
            password="StrongPassword@123!",
            role="admin",
        )
        self.org_other = Organization.objects.create(name="Other Group", code="OTHORG", owner=self.principal_other)
        self.school_other = School.objects.create(name="Other School", code="OTHR", principal=self.principal_other)
        self.school_org_other = SchoolOrganization.objects.create(
            organization=self.org_other,
            school=self.school_other,
            status="active",
        )
        OrganizationMember.objects.create(
            organization=self.org_other,
            user=self.principal_other,
            role="owner",
        )
        self.class_10a = SchoolClass.objects.create(school=self.school, name="10", section="A")
        self.class_other_10a = SchoolClass.objects.create(school=self.school_other, name="10", section="A")

    def test_template_downloads(self):
        self.client.force_authenticate(user=self.principal)

        res_t = self.client.get("/api/v1/import/template/teachers/")
        self.assertEqual(res_t.status_code, status.HTTP_200_OK)
        self.assertEqual(res_t["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("teacher_import_template.xlsx", res_t["Content-Disposition"])

        res_s = self.client.get("/api/v1/import/template/students/")
        self.assertEqual(res_s.status_code, status.HTTP_200_OK)
        self.assertEqual(res_s["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("student_import_template.xlsx", res_s["Content-Disposition"])

    def test_formula_injection_sanitization_and_dry_run_teacher(self):
        self.client.force_authenticate(user=self.principal)

        headers = ["Employee ID*", "First Name*", "Last Name*", "Email", "Mobile*", "Designation", "Department"]
        rows = [
            ["=SUM(1,2)", "Rajesh", "Sharma", "rajesh@example.com", "9876543210", "Maths Teacher", "Science"],
            ["EMP002", "+CMD|' /C calc'!A0", "Verma", "verma@example.com", "9876543211", "English Teacher", "Arts"],
        ]
        xlsx_bytes = create_excel_file(headers, rows)
        uploaded = SimpleUploadedFile("teachers.xlsx", xlsx_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        res = self.client.post(
            "/api/v1/import/preview/",
            {"type": "teacher", "file": uploaded},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["validRows"], 2)
        self.assertEqual(res.data["errorRows"], 0)

        # Confirm and check formula injection escaping
        token = res.data["importToken"]
        res_confirm = self.client.post("/api/v1/import/confirm/", {"importToken": token})
        self.assertEqual(res_confirm.status_code, status.HTTP_200_OK)
        self.assertIn("Cache-Control", res_confirm)
        self.assertIn("no-store", res_confirm["Cache-Control"])

        # Check in DB that formula characters were escaped with leading quote
        t1 = Teacher.objects.filter(school=self.school).first()
        self.assertTrue(t1.employee_id.endswith("'=SUM(1+1)") or "'=SUM" in t1.employee_id)

    def test_teacher_validation_errors_duplicate_and_bad_mobile(self):
        self.client.force_authenticate(user=self.principal)

        headers = ["Employee ID*", "First Name*", "Last Name*", "Email", "Mobile*", "Designation", "Department"]
        rows = [
            ["EMP001", "Aman", "Gupta", "aman@example.com", "123", "Teacher", "Science"],  # Bad mobile
            ["EMP001", "Ankit", "Gupta", "ankit@example.com", "9876543210", "Teacher", "Science"],  # Duplicate in file
            ["EMP003", "", "Gupta", "ankit@example.com", "9876543210", "Teacher", "Science"],  # Missing first name
        ]
        xlsx_bytes = create_excel_file(headers, rows)
        uploaded = SimpleUploadedFile("teachers.xlsx", xlsx_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        res = self.client.post(
            "/api/v1/import/preview/",
            {"type": "teacher", "file": uploaded},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["validRows"], 0)
        self.assertEqual(res.data["errorRows"], 3)
        self.assertIn("Invalid mobile number", str(res.data["errors"]))
        self.assertIn("Duplicate Employee ID", str(res.data["errors"]))
        self.assertIn("First name is required", str(res.data["errors"]))

    def test_student_validation_wrong_class_and_duplicate_admission_number(self):
        self.client.force_authenticate(user=self.principal)

        headers = [
            "Admission Number*", "First Name*", "Last Name*", "Class*", "Section*",
            "Guardian Name*", "Guardian Mobile*", "Guardian Relation*",
        ]
        rows = [
            # Wrong class (12 B doesn't exist)
            ["ADM101", "Rahul", "Singh", "12", "B", "Vikram Singh", "9876543210", "father"],
            # Duplicate admission number within this sheet
            ["ADM101", "Mohan", "Lal", "10", "A", "Shyam Lal", "9876543211", "father"],
        ]
        xlsx_bytes = create_excel_file(headers, rows)
        uploaded = SimpleUploadedFile("students.xlsx", xlsx_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        res = self.client.post(
            "/api/v1/import/preview/",
            {"type": "student", "file": uploaded},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["validRows"], 0)
        self.assertEqual(res.data["errorRows"], 2)
        errors_str = str(res.data["errors"])
        self.assertIn("does not exist in your school", errors_str)
        self.assertIn("Duplicate Admission Number", errors_str)

    def test_student_import_sibling_guardian_deduplication_and_parent_user(self):
        self.client.force_authenticate(user=self.principal)

        headers = [
            "Admission Number*", "First Name*", "Last Name*", "Class*", "Section*",
            "Guardian Name*", "Guardian Mobile*", "Guardian Relation*",
        ]
        # Two siblings sharing the same guardian mobile
        rows = [
            ["ADM201", "Pooja", "Patel", "10", "A", "Harish Patel", "9826012345", "father"],
            ["ADM202", "Priya", "Patel", "10", "A", "Harish Patel", "9826012345", "father"],
        ]
        xlsx_bytes = create_excel_file(headers, rows)
        uploaded = SimpleUploadedFile("students.xlsx", xlsx_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        res = self.client.post(
            "/api/v1/import/preview/",
            {"type": "student", "file": uploaded},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        token = res.data["importToken"]

        res_confirm = self.client.post("/api/v1/import/confirm/", {"importToken": token})
        self.assertEqual(res_confirm.status_code, status.HTTP_200_OK)

        # Verify only 1 Guardian record created for Harish Patel
        guardians = Guardian.objects.filter(school=self.school, mobile="9826012345")
        self.assertEqual(guardians.count(), 1)
        guardian = guardians.first()
        self.assertEqual(guardian.link_status, "approved")

        # Verify parent user was created with username = normalized 10-digit mobile
        parent_user = User.objects.filter(username="9826012345").first()
        self.assertIsNotNone(parent_user)
        self.assertEqual(parent_user.role, "parent")
        self.assertEqual(guardian.user, parent_user)
        self.assertTrue(parent_user.security.must_change_password)

        # Verify both students linked to the single guardian
        self.assertEqual(StudentGuardian.objects.filter(guardian=guardian).count(), 2)

        # Audit log verified
        audit = AuditLog.objects.filter(action="import.students", school=self.school).first()
        self.assertIsNotNone(audit)

    def test_pending_school_blocked_from_import_confirm(self):
        # Set school status to pending
        self.school_org.status = "pending"
        self.school_org.save()

        self.client.force_authenticate(user=self.principal)

        headers = ["Employee ID*", "First Name*", "Last Name*", "Email", "Mobile*", "Designation", "Department"]
        rows = [["EMP100", "Sunil", "Jain", "sunil@example.com", "9876543210", "Teacher", "Science"]]
        xlsx_bytes = create_excel_file(headers, rows)
        uploaded = SimpleUploadedFile("teachers.xlsx", xlsx_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # Dry run / preview is allowed even if pending (Decision 3)
        res_preview = self.client.post(
            "/api/v1/import/preview/",
            {"type": "teacher", "file": uploaded},
            format="multipart",
        )
        self.assertEqual(res_preview.status_code, status.HTTP_200_OK)
        token = res_preview.data["importToken"]

        # Confirm is BLOCKED when pending
        res_confirm = self.client.post("/api/v1/import/confirm/", {"importToken": token})
        self.assertEqual(res_confirm.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_confirm.data.get("code"), "EMAIL_VERIFICATION_PENDING")

    def test_import_idempotent_reupload(self):
        self.client.force_authenticate(user=self.principal)

        headers = ["Employee ID*", "First Name*", "Last Name*", "Email", "Mobile*", "Designation", "Department"]
        rows = [["EMP500", "Anita", "Sharma", "anita@example.com", "9876543210", "Lecturer", "English"]]
        xlsx_bytes = create_excel_file(headers, rows)

        # 1st upload
        uploaded = SimpleUploadedFile("teachers.xlsx", xlsx_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res1 = self.client.post("/api/v1/import/preview/", {"type": "teacher", "file": uploaded}, format="multipart")
        token1 = res1.data["importToken"]
        self.client.post("/api/v1/import/confirm/", {"importToken": token1})

        self.assertEqual(Teacher.objects.filter(school=self.school, employee_id=f"{self.school.code}-EMP500").count(), 1)
        t_user = Teacher.objects.get(school=self.school, employee_id=f"{self.school.code}-EMP500").user
        self.assertEqual(t_user.first_name, "Anita")

        # 2nd upload with updated designation and name
        rows_updated = [["EMP500", "Anita", "Verma", "anita@example.com", "9876543210", "Head of Dept", "English"]]
        xlsx_bytes2 = create_excel_file(headers, rows_updated)
        uploaded2 = SimpleUploadedFile("teachers.xlsx", xlsx_bytes2, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res2 = self.client.post("/api/v1/import/preview/", {"type": "teacher", "file": uploaded2}, format="multipart")
        token2 = res2.data["importToken"]
        self.client.post("/api/v1/import/confirm/", {"importToken": token2})

        # Count should still be 1, updated
        self.assertEqual(Teacher.objects.filter(school=self.school, employee_id=f"{self.school.code}-EMP500").count(), 1)
        t_updated = Teacher.objects.get(school=self.school, employee_id=f"{self.school.code}-EMP500")
        self.assertEqual(t_updated.user.last_name, "Verma")
        self.assertEqual(t_updated.designation, "Head of Dept")

    def test_token_replay_prevention(self):
        self.client.force_authenticate(user=self.principal)

        headers = ["Employee ID*", "First Name*", "Last Name*", "Email", "Mobile*", "Designation", "Department"]
        rows = [["EMP700", "Deepak", "Sharma", "deepak@example.com", "9876543210", "Teacher", "Science"]]
        xlsx_bytes = create_excel_file(headers, rows)
        uploaded = SimpleUploadedFile("teachers.xlsx", xlsx_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        res = self.client.post("/api/v1/import/preview/", {"type": "teacher", "file": uploaded}, format="multipart")
        token = res.data["importToken"]

        res_first = self.client.post("/api/v1/import/confirm/", {"importToken": token})
        self.assertEqual(res_first.status_code, status.HTTP_200_OK)

        # Replaying same token should fail
        res_replay = self.client.post("/api/v1/import/confirm/", {"importToken": token})
        self.assertEqual(res_replay.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_import_class_normalization_and_available_classes(self):
        self.client.force_authenticate(user=self.principal)

        # Create 10-B as well to test available classes list formatting
        class_10b = SchoolClass.objects.create(school=self.school, name="10", section="B")

        headers = [
            "Admission Number*", "First Name*", "Last Name*", "Class*", "Section*",
            "Guardian Name*", "Guardian Mobile*", "Guardian Relation*",
        ]
        rows = [
            # 1. "Class 10" vs "10" and lowercase section "a"
            ["ADM301", "Kavya", "Sharma", "Class 10", "a", "Manoj Sharma", "9876543201", "father"],
            # 2. Text cell "10" with section "A"
            ["ADM302", "Rohit", "Verma", "10", "A", "Sunil Verma", "9876543202", "father"],
            # 3. Numeric cell 10 vs text cell and lowercase section "b"
            ["ADM303", "Ananya", "Joshi", 10, "b", "Alok Joshi", "9876543203", "mother"],
            # 4. "std 10" with whitespace in section
            ["ADM304", "Vikas", "Dubey", "std 10", " a ", "Rajesh Dubey", "9876543204", "father"],
            # 5. "Standard 10" with uppercase section
            ["ADM305", "Meera", "Sen", "Standard 10", "B", "Ashok Sen", "9876543205", "mother"],
        ]
        xlsx_bytes = create_excel_file(headers, rows)
        uploaded = SimpleUploadedFile("students.xlsx", xlsx_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        res_preview = self.client.post(
            "/api/v1/import/preview/",
            {"type": "student", "file": uploaded},
            format="multipart",
        )
        self.assertEqual(res_preview.status_code, status.HTTP_200_OK)
        self.assertEqual(res_preview.data["validRows"], 5)
        self.assertEqual(res_preview.data["errorRows"], 0)

        # Confirm and check all 5 are linked to the right SchoolClass objects
        token = res_preview.data["importToken"]
        res_confirm = self.client.post("/api/v1/import/confirm/", {"importToken": token})
        self.assertEqual(res_confirm.status_code, status.HTTP_200_OK)

        # Verify students and class links
        s1 = Student.objects.get(school=self.school, admission_number=f"{self.school.code}-ADM301")
        self.assertEqual(s1.class_section, self.class_10a)

        s2 = Student.objects.get(school=self.school, admission_number=f"{self.school.code}-ADM302")
        self.assertEqual(s2.class_section, self.class_10a)

        s3 = Student.objects.get(school=self.school, admission_number=f"{self.school.code}-ADM303")
        self.assertEqual(s3.class_section, class_10b)

        s4 = Student.objects.get(school=self.school, admission_number=f"{self.school.code}-ADM304")
        self.assertEqual(s4.class_section, self.class_10a)

        s5 = Student.objects.get(school=self.school, admission_number=f"{self.school.code}-ADM305")
        self.assertEqual(s5.class_section, class_10b)

        # Now test invalid class and verify available classes are listed in error message
        bad_rows = [
            ["ADM399", "Unknown", "Student", "12", "C", "Parent Name", "9876543299", "father"],
        ]
        bad_xlsx = create_excel_file(headers, bad_rows)
        bad_upload = SimpleUploadedFile("bad_students.xlsx", bad_xlsx, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        res_bad = self.client.post(
            "/api/v1/import/preview/",
            {"type": "student", "file": bad_upload},
            format="multipart",
        )
        self.assertEqual(res_bad.status_code, status.HTTP_200_OK)
        self.assertEqual(res_bad.data["validRows"], 0)
        self.assertEqual(res_bad.data["errorRows"], 1)
        err_msg = str(res_bad.data["errors"])
        self.assertIn("does not exist in your school", err_msg)
        self.assertIn("Available: 10-A, 10-B", err_msg)

    def test_same_admission_number_in_two_schools(self):
        """Two schools can have students with the same admission number without collision."""
        headers = [
            "Admission Number*", "First Name*", "Last Name*", "Class*", "Section*",
            "Guardian Name*", "Guardian Mobile*", "Guardian Relation*",
        ]

        # 1. School 1 imports student with ADM-SAME-01
        self.client.force_authenticate(user=self.principal)
        rows_1 = [["ADM-SAME-01", "Aarav", "Sharma", "10", "A", "G1", "9826011111", "father"]]
        xlsx_1 = create_excel_file(headers, rows_1)
        f1 = SimpleUploadedFile("s1.xlsx", xlsx_1, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res1_prev = self.client.post("/api/v1/import/preview/", {"type": "student", "file": f1}, format="multipart")
        self.assertEqual(res1_prev.status_code, status.HTTP_200_OK)
        self.assertEqual(res1_prev.data["validRows"], 1)
        res1_conf = self.client.post("/api/v1/import/confirm/", {"importToken": res1_prev.data["importToken"]})
        self.assertEqual(res1_conf.status_code, status.HTTP_200_OK)

        # 2. School 2 imports student with identical ADM-SAME-01
        self.client.force_authenticate(user=self.principal_other)
        rows_2 = [["ADM-SAME-01", "Vivaan", "Joshi", "10", "A", "G2", "9826022222", "father"]]
        xlsx_2 = create_excel_file(headers, rows_2)
        f2 = SimpleUploadedFile("s2.xlsx", xlsx_2, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res2_prev = self.client.post("/api/v1/import/preview/", {"type": "student", "file": f2}, format="multipart")
        self.assertEqual(res2_prev.status_code, status.HTTP_200_OK)
        self.assertEqual(res2_prev.data["validRows"], 1)
        res2_conf = self.client.post("/api/v1/import/confirm/", {"importToken": res2_prev.data["importToken"]})
        self.assertEqual(res2_conf.status_code, status.HTTP_200_OK)

        # Check DB: internal storage has schoolcode prefix
        std_1 = Student.objects.get(school=self.school, admission_number=f"{self.school.code}-ADM-SAME-01")
        std_2 = Student.objects.get(school=self.school_other, admission_number=f"{self.school_other.code}-ADM-SAME-01")

        # Serializer displays without prefix
        from api.serializers import StudentSerializer
        self.assertEqual(StudentSerializer(std_1).data["admissionNumber"], "ADM-SAME-01")
        self.assertEqual(StudentSerializer(std_2).data["admissionNumber"], "ADM-SAME-01")

    def test_sibling_across_two_schools_with_one_parent_user(self):
        """Sibling attending another school reuses the single parent user account."""
        headers = [
            "Admission Number*", "First Name*", "Last Name*", "Class*", "Section*",
            "Guardian Name*", "Guardian Mobile*", "Guardian Relation*",
        ]

        # 1. School 1 imports elder sibling with parent mobile 9826033333
        self.client.force_authenticate(user=self.principal)
        rows_1 = [["ADM-SIB-1", "Aditi", "Patel", "10", "A", "Rajesh Patel", "9826033333", "father"]]
        xlsx_1 = create_excel_file(headers, rows_1)
        f1 = SimpleUploadedFile("s1.xlsx", xlsx_1, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res1_prev = self.client.post("/api/v1/import/preview/", {"type": "student", "file": f1}, format="multipart")
        self.client.post("/api/v1/import/confirm/", {"importToken": res1_prev.data["importToken"]})

        parent_u = User.objects.get(username="9826033333")
        self.assertEqual(parent_u.security.created_via, "import")
        self.assertEqual(Guardian.objects.filter(user=parent_u, school=self.school, link_status="approved").count(), 1)

        # 2. School 2 imports younger sibling with same parent mobile 9826033333
        self.client.force_authenticate(user=self.principal_other)
        rows_2 = [["ADM-SIB-2", "Ananya", "Patel", "10", "A", "Rajesh Patel", "9826033333", "father"]]
        xlsx_2 = create_excel_file(headers, rows_2)
        f2 = SimpleUploadedFile("s2.xlsx", xlsx_2, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res2_prev = self.client.post("/api/v1/import/preview/", {"type": "student", "file": f2}, format="multipart")
        self.assertEqual(res2_prev.status_code, status.HTTP_200_OK)
        self.assertEqual(res2_prev.data["validRows"], 1)
        self.client.post("/api/v1/import/confirm/", {"importToken": res2_prev.data["importToken"]})

        # Only one parent user exists in total
        self.assertEqual(User.objects.filter(username="9826033333").count(), 1)
        # Guardian records created for both schools
        self.assertEqual(Guardian.objects.filter(user=parent_u).count(), 2)
        self.assertTrue(Guardian.objects.filter(user=parent_u, school=self.school_other, link_status="approved").exists())

    def test_squatted_numeric_username_and_non_import_user_blocked(self):
        """Block 10-digit usernames in public registration and block non-import users from being reused by student import."""
        # 1. Public registration rejects 10-digit numeric username
        res_reg = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "9826099999",
                "password": "StrongPassword@123!",
                "role": "parent",
                "email": "test99@example.com",
            },
        )
        self.assertEqual(res_reg.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("10-digit numeric usernames are reserved", str(res_reg.data))

        # 2. Pre-existing non-import account exists
        manual_u = User.objects.create_user(
            username="9826088888",
            password="ManualPassword@123!",
            role="teacher",
        )
        # Default security created_via is 'manual', no approved guardian links
        headers = [
            "Admission Number*", "First Name*", "Last Name*", "Class*", "Section*",
            "Guardian Name*", "Guardian Mobile*", "Guardian Relation*",
        ]
        rows = [["ADM-BLOCKED", "Rohan", "Mehta", "10", "A", "Ramesh Mehta", "9826088888", "father"]]
        xlsx = create_excel_file(headers, rows)
        f = SimpleUploadedFile("s.xlsx", xlsx, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.client.force_authenticate(user=self.principal)
        res_prev = self.client.post("/api/v1/import/preview/", {"type": "student", "file": f}, format="multipart")
        self.assertEqual(res_prev.status_code, status.HTTP_200_OK)
        self.assertEqual(res_prev.data["validRows"], 0)
        self.assertEqual(res_prev.data["errorRows"], 1)
        self.assertIn("already registered by another account", str(res_prev.data["errors"]))

    def test_existing_parent_password_untouched(self):
        """When an existing parent is reused, their password is never changed and sheet marks 'Existing account'."""
        headers = [
            "Admission Number*", "First Name*", "Last Name*", "Class*", "Section*",
            "Guardian Name*", "Guardian Mobile*", "Guardian Relation*",
        ]

        # 1. School imports 1st student
        self.client.force_authenticate(user=self.principal)
        rows_1 = [["ADM-PW-1", "Karan", "Kapoor", "10", "A", "Rishi Kapoor", "9826044444", "father"]]
        xlsx_1 = create_excel_file(headers, rows_1)
        f1 = SimpleUploadedFile("s1.xlsx", xlsx_1, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res1_prev = self.client.post("/api/v1/import/preview/", {"type": "student", "file": f1}, format="multipart")
        res1_conf = self.client.post("/api/v1/import/confirm/", {"importToken": res1_prev.data["importToken"]})
        self.assertEqual(res1_conf.status_code, status.HTTP_200_OK)

        parent_u = User.objects.get(username="9826044444")
        initial_pw_hash = parent_u.password

        # 2. School imports 2nd student (sibling) with same guardian mobile
        rows_2 = [["ADM-PW-2", "Kavya", "Kapoor", "10", "A", "Rishi Kapoor", "9826044444", "father"]]
        xlsx_2 = create_excel_file(headers, rows_2)
        f2 = SimpleUploadedFile("s2.xlsx", xlsx_2, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res2_prev = self.client.post("/api/v1/import/preview/", {"type": "student", "file": f2}, format="multipart")
        self.assertEqual(res2_prev.data["validRows"], 1)
        res2_conf = self.client.post("/api/v1/import/confirm/", {"importToken": res2_prev.data["importToken"]})
        self.assertEqual(res2_conf.status_code, status.HTTP_200_OK)

        # Verify password in DB was NOT touched
        parent_u.refresh_from_db()
        self.assertEqual(parent_u.password, initial_pw_hash)

        # Verify credentials sheet has "Existing account" for parent row
        wb = openpyxl.load_workbook(io.BytesIO(res2_conf.content))
        ws = wb.active
        parent_found = False
        for row in ws.iter_rows(values_only=True):
            # Column headers: [Type, Name, Identifier, Username, Password, Note]
            if len(row) >= 5 and row[0] == "Parent":
                parent_found = True
                self.assertEqual(row[4], "Existing account")
        self.assertTrue(parent_found)

