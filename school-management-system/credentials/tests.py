from django.contrib.auth.password_validation import validate_password
from rest_framework import status
from rest_framework.test import APITestCase

from academics.models import Teacher
from accounts.models import User
from audit.models import AuditLog
from credentials.models import UserSecurity
from credentials.services import generate_random_password, generate_username
from schools.models import School


class CredentialsTests(APITestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="School A", code="SCHA")
        self.school_b = School.objects.create(name="School B", code="SCHB")

        self.principal_a = User.objects.create_user(
            username="principal_a",
            email="principal_a@example.com",
            password="StrongPassword@123!",
            role="principal",
        )
        self.school_a.principal = self.principal_a
        self.school_a.save()

        self.teacher_a_user = User.objects.create_user(
            username="teacher_a",
            email="teacher_a@example.com",
            password="TeacherPassword@123!",
            role="teacher",
        )
        self.teacher_a = Teacher.objects.create(
            user=self.teacher_a_user,
            school=self.school_a,
            employee_id="EMP-A-1",
        )

        self.teacher_b_user = User.objects.create_user(
            username="teacher_b",
            email="teacher_b@example.com",
            password="TeacherPassword@123!",
            role="teacher",
        )
        self.teacher_b = Teacher.objects.create(
            user=self.teacher_b_user,
            school=self.school_b,
            employee_id="EMP-B-1",
        )

    def test_username_generator_format_and_uniqueness(self):
        u1 = generate_username("DPS-09", "T", "EMP101")
        self.assertEqual(u1, "DPS09-T-EMP101")

        # Create a user with this username
        User.objects.create_user(username=u1, password="SomePassword@123!")

        # Generating again should produce a collision-free suffix
        u2 = generate_username("DPS-09", "T", "EMP101")
        self.assertEqual(u2, "DPS09-T-EMP101-1")

    def test_random_password_generator_meets_django_complexity(self):
        for _ in range(5):
            pwd = generate_random_password(12)
            self.assertGreaterEqual(len(pwd), 12)
            # Should not raise any ValidationError
            validate_password(pwd)

    def test_must_change_password_blocks_normal_endpoints_until_changed(self):
        sec, _ = UserSecurity.objects.get_or_create(user=self.teacher_a_user)
        sec.must_change_password = True
        sec.save()

        self.client.force_login(self.teacher_a_user)

        # Attempt to access a normal endpoint
        res = self.client.get("/api/v1/teacher/my-students/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        data = res.data if hasattr(res, "data") else res.json()
        self.assertEqual(data.get("code"), "MUST_CHANGE_PASSWORD")

        # Whitelisted endpoint /auth/me/ should succeed
        res_me = self.client.get("/api/v1/auth/me/")
        self.assertEqual(res_me.status_code, status.HTTP_200_OK)

        # Change password
        res_change = self.client.post(
            "/api/v1/auth/change-password/",
            {
                "oldPassword": "TeacherPassword@123!",
                "newPassword": "NewSecurePassword@999!",
            },
        )
        self.assertEqual(res_change.status_code, status.HTTP_200_OK)

        # Flag should now be cleared
        sec.refresh_from_db()
        self.assertFalse(sec.must_change_password)

        # Now access should be allowed
        res_after = self.client.get("/api/v1/teacher/my-students/")
        self.assertEqual(res_after.status_code, status.HTTP_200_OK)

    def test_principal_password_reset_creates_audit_log_and_isolation(self):
        self.client.force_authenticate(user=self.principal_a)

        # Reset teacher in same school
        res = self.client.post(
            "/api/v1/credentials/reset-password/",
            {"userId": self.teacher_a_user.id},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        temp_pwd = res.data["temporaryPassword"]
        self.assertTrue(temp_pwd)

        # Verify teacher can log in with temp_pwd
        self.teacher_a_user.refresh_from_db()
        self.assertTrue(self.teacher_a_user.check_password(temp_pwd))
        self.assertTrue(self.teacher_a_user.security.must_change_password)

        # Verify audit log
        audit = AuditLog.objects.filter(action="credentials.reset", object_id=self.teacher_a_user.id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.principal_a)
        self.assertEqual(audit.school, self.school_a)

        # Attempt to reset teacher in different school (school_b) -> 403 Forbidden
        res_cross = self.client.post(
            "/api/v1/credentials/reset-password/",
            {"userId": self.teacher_b_user.id},
        )
        self.assertEqual(res_cross.status_code, status.HTTP_403_FORBIDDEN)

    def test_plaintext_passwords_never_persisted(self):
        self.client.force_authenticate(user=self.principal_a)
        res = self.client.post(
            "/api/v1/credentials/reset-password/",
            {"userId": self.teacher_a_user.id},
        )
        temp_pwd = res.data["temporaryPassword"]

        self.teacher_a_user.refresh_from_db()
        # Stored password must be a pbkdf2 hash, never plaintext
        self.assertNotEqual(self.teacher_a_user.password, temp_pwd)
        self.assertTrue(self.teacher_a_user.password.startswith("pbkdf2_sha256$"))

    def test_change_password_validations(self):
        self.client.force_login(self.teacher_a_user)

        # Same as old password
        res = self.client.post(
            "/api/v1/auth/change-password/",
            {"oldPassword": "TeacherPassword@123!", "newPassword": "TeacherPassword@123!"},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot be the same as the old password", str(res.data))

        # Same as username
        res = self.client.post(
            "/api/v1/auth/change-password/",
            {"oldPassword": "TeacherPassword@123!", "newPassword": "teacher_a"},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot be the same as your username", str(res.data))

        # Same as employee ID
        res = self.client.post(
            "/api/v1/auth/change-password/",
            {"oldPassword": "TeacherPassword@123!", "newPassword": "EMP-A-1"},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot be your employee ID", str(res.data))

        # Too short / common
        res = self.client.post(
            "/api/v1/auth/change-password/",
            {"oldPassword": "TeacherPassword@123!", "newPassword": "short"},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Valid strong password
        res = self.client.post(
            "/api/v1/auth/change-password/",
            {"oldPassword": "TeacherPassword@123!", "newPassword": "BrandNewValidPassword@999!"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_reissue_credentials_skips_users_who_changed_password_and_isolation(self):
        import io
        import openpyxl
        from organizations.models import Organization, OrganizationMember, SchoolOrganization

        org = Organization.objects.create(name="Org Test", code="ORGTEST", owner=self.principal_a)
        SchoolOrganization.objects.create(school=self.school_a, organization=org, status="active")

        # Teacher 1: import + must_change_password=True -> MUST be reissued
        UserSecurity.objects.update_or_create(
            user=self.teacher_a_user,
            defaults={"created_via": "import", "must_change_password": True},
        )
        self.teacher_a_user.mobile = "9876543210"
        self.teacher_a_user.save()

        # Teacher 2: import + must_change_password=False -> MUST BE SKIPPED
        t2_user = User.objects.create_user(
            username="teacher_a2",
            email="t2@example.com",
            password="TeacherPassword@123!",
            role="teacher",
            mobile="9876543211",
        )
        Teacher.objects.create(user=t2_user, school=self.school_a, employee_id="EMP-A-2")
        UserSecurity.objects.create(user=t2_user, created_via="import", must_change_password=False)

        # Teacher 3: manual + must_change_password=True -> MUST BE SKIPPED
        t3_user = User.objects.create_user(
            username="teacher_a3",
            email="t3@example.com",
            password="TeacherPassword@123!",
            role="teacher",
            mobile="9876543212",
        )
        Teacher.objects.create(user=t3_user, school=self.school_a, employee_id="EMP-A-3")
        UserSecurity.objects.create(user=t3_user, created_via="manual", must_change_password=True)

        # Teacher B: in school B -> MUST NOT BE TOUCHED
        UserSecurity.objects.create(user=self.teacher_b_user, created_via="import", must_change_password=True)
        old_tb_pass = self.teacher_b_user.password

        self.client.force_login(self.principal_a)
        res = self.client.post(
            "/api/v1/credentials/reissue/",
            {"scope": "teachers", "passwordMode": "id_pattern"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res["Cache-Control"], "no-store, no-cache, must-revalidate, max-age=0")
        self.assertEqual(res["X-Reissued-Count"], "1")
        self.assertEqual(res["X-Skipped-Count"], "2")

        # Verify audit log
        audit = AuditLog.objects.filter(action="credentials.reissue", school=self.school_a).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.changes["reissued_count"], 1)
        self.assertEqual(audit.changes["skipped_count"], 2)

        # Teacher B untouched
        self.teacher_b_user.refresh_from_db()
        self.assertEqual(self.teacher_b_user.password, old_tb_pass)

        # Teacher 2 untouched
        t2_user.refresh_from_db()
        self.assertTrue(t2_user.check_password("TeacherPassword@123!"))

        # Verify returned xlsx contains id_pattern for Teacher 1: "<EmployeeID>@<last4 of mobile>"
        # Teacher 1 display ID is "EMP-A-1", mobile last4 is "3210" -> "EMP-A-1@3210"
        wb = openpyxl.load_workbook(io.BytesIO(res.content))
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        # Header is at row 4 (index 3), data starts at row 5 (index 4)
        data_rows = rows[4:]
        self.assertEqual(len(data_rows), 1)
        row1 = data_rows[0]
        # Column 5 (index 4) is password
        self.assertEqual(row1[4], "EMP-A-1@3210")

    def test_reissue_credentials_pending_school_blocked(self):
        from organizations.models import Organization, SchoolOrganization
        org = Organization.objects.create(name="Org Pending", code="ORGPEND", owner=self.principal_a)
        SchoolOrganization.objects.create(school=self.school_a, organization=org, status="pending")

        self.client.force_login(self.principal_a)
        res = self.client.post(
            "/api/v1/credentials/reissue/",
            {"scope": "teachers", "passwordMode": "random"},
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        data = res.json()
        self.assertEqual(data.get("code"), "EMAIL_VERIFICATION_PENDING")

    def test_reissue_credentials_students_and_parent_immunity(self):
        from academics.models import SchoolClass, Student
        from guardians.models import Guardian, StudentGuardian
        from organizations.models import Organization, SchoolOrganization

        org = Organization.objects.create(name="Org S", code="ORGS", owner=self.principal_a)
        SchoolOrganization.objects.create(school=self.school_a, organization=org, status="active")

        s_class = SchoolClass.objects.create(name="Class 10", section="A", school=self.school_a)

        parent_user = User.objects.create_user(
            username="9876543299",
            email="p@example.com",
            password="ParentInitialPassword@123!",
            role="parent",
            mobile="9876543299",
        )
        # Parent already changed password: must_change_password=False
        UserSecurity.objects.create(user=parent_user, created_via="import", must_change_password=False)

        guardian = Guardian.objects.create(
            school=self.school_a,
            full_name="Parent Guardian",
            mobile="9876543299",
            user=parent_user,
            link_status="approved",
        )

        student_user = User.objects.create_user(
            username="SCHA-S-ADM100",
            email="s@example.com",
            password="TempStudentPassword@123!",
            role="student",
        )
        UserSecurity.objects.create(user=student_user, created_via="import", must_change_password=True)
        student = Student.objects.create(
            user=student_user,
            school=self.school_a,
            class_section=s_class,
            admission_number="SCHA-ADM100",
        )
        StudentGuardian.objects.create(student=student, guardian=guardian, is_primary=True)

        self.client.force_login(self.principal_a)

        # Reissue scope=parents -> parent has must_change_password=False, must be skipped
        res_p = self.client.post("/api/v1/credentials/reissue/", {"scope": "parents"})
        self.assertEqual(res_p.status_code, status.HTTP_200_OK)
        self.assertEqual(res_p["X-Reissued-Count"], "0")
        self.assertEqual(res_p["X-Skipped-Count"], "1")
        parent_user.refresh_from_db()
        self.assertTrue(parent_user.check_password("ParentInitialPassword@123!"))

        # Reissue scope=class -> student has must_change_password=True -> reissued
        res_s = self.client.post(
            "/api/v1/credentials/reissue/",
            {"scope": "class", "classId": s_class.id, "passwordMode": "id_pattern"},
        )
        self.assertEqual(res_s.status_code, status.HTTP_200_OK)
        self.assertEqual(res_s["X-Reissued-Count"], "1")
        self.assertEqual(res_s["X-Skipped-Count"], "0")
        student_user.refresh_from_db()
        # id_pattern for student: "<AdmissionNo>@<last4 of guardian mobile>"
        # "ADM100@3299"
        self.assertTrue(student_user.check_password("ADM100@3299"))

