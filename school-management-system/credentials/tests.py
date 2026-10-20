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
