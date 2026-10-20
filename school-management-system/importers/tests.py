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

        # Another school for tenant isolation checks
        self.school_other = School.objects.create(name="Other School", code="OTHR")
        self.class_10a = SchoolClass.objects.create(school=self.school, name="10", section="A")

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
        self.assertTrue(t1.employee_id.startswith("'=SUM"))

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

    def test_student_validation_wrong_class_and_cross_school_duplicate(self):
        self.client.force_authenticate(user=self.principal)

        # Create student in other school with ADM999
        other_user = User.objects.create_user(username="other_std", password="Password@123!")
        Student.objects.create(
            user=other_user,
            school=self.school_other,
            admission_number="ADM999",
        )

        headers = [
            "Admission Number*", "First Name*", "Last Name*", "Class*", "Section*",
            "Guardian Name*", "Guardian Mobile*", "Guardian Relation*",
        ]
        rows = [
            # Wrong class (12 B doesn't exist)
            ["ADM101", "Rahul", "Singh", "12", "B", "Vikram Singh", "9876543210", "father"],
            # Cross-school duplicate admission number
            ["ADM999", "Mohan", "Lal", "10", "A", "Shyam Lal", "9876543211", "father"],
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
        self.assertIn("already registered at another school", errors_str)

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

        self.assertEqual(Teacher.objects.filter(school=self.school, employee_id="EMP500").count(), 1)
        t_user = Teacher.objects.get(school=self.school, employee_id="EMP500").user
        self.assertEqual(t_user.first_name, "Anita")

        # 2nd upload with updated designation and name
        rows_updated = [["EMP500", "Anita", "Verma", "anita@example.com", "9876543210", "Head of Dept", "English"]]
        xlsx_bytes2 = create_excel_file(headers, rows_updated)
        uploaded2 = SimpleUploadedFile("teachers.xlsx", xlsx_bytes2, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res2 = self.client.post("/api/v1/import/preview/", {"type": "teacher", "file": uploaded2}, format="multipart")
        token2 = res2.data["importToken"]
        self.client.post("/api/v1/import/confirm/", {"importToken": token2})

        # Count should still be 1, updated
        self.assertEqual(Teacher.objects.filter(school=self.school, employee_id="EMP500").count(), 1)
        t_updated = Teacher.objects.get(school=self.school, employee_id="EMP500")
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
