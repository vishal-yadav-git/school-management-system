from django.core.cache import cache
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from audit.services import log_action
from schools.models import School


class AuditTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Superuser
        self.superuser = User.objects.create_superuser(
            username="admin_root",
            password="Password@123",
            email="root@indore.edu",
        )

        # School A and Principal A
        self.school_a = School.objects.create(name="School A", code="SCH-A", address="Road A", city="Indore")
        self.principal_a = User.objects.create_user(
            username="principal_a",
            password="Password@123",
            role="principal",
        )
        self.school_a.principal = self.principal_a
        self.school_a.save()

        # School B and Principal B
        self.school_b = School.objects.create(name="School B", code="SCH-B", address="Road B", city="Indore")
        self.principal_b = User.objects.create_user(
            username="principal_b",
            password="Password@123",
            role="principal",
        )
        self.school_b.principal = self.principal_b
        self.school_b.save()

        # Non-principal users
        self.teacher_user = User.objects.create_user(
            username="teacher_user",
            password="Password@123",
            role="teacher",
        )
        self.student_user = User.objects.create_user(
            username="student_user",
            password="Password@123",
            role="student",
        )
        self.parent_user = User.objects.create_user(
            username="parent_user",
            password="Password@123",
            role="parent",
        )

    def test_audit_row_created_for_academic_year_actions(self):
        self.client.force_authenticate(user=self.principal_a)

        # Create an academic year with isCurrent=True
        res = self.client.post(
            "/api/v1/academic-years/",
            data={
                "name": "2026-27",
                "startDate": "2026-04-01",
                "endDate": "2027-03-31",
                "isCurrent": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Check AuditLog table directly
        create_logs = AuditLog.objects.filter(school=self.school_a, action="academic_year.create")
        self.assertEqual(create_logs.count(), 1)
        self.assertEqual(create_logs.first().actor, self.principal_a)

        set_current_logs = AuditLog.objects.filter(school=self.school_a, action="academic_year.set_current")
        self.assertEqual(set_current_logs.count(), 1)

        # Query GET /api/v1/audit/
        res_audit = self.client.get("/api/v1/audit/")
        self.assertEqual(res_audit.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res_audit.data), 2)
        actions = [entry["action"] for entry in res_audit.data]
        self.assertIn("academic_year.create", actions)
        self.assertIn("academic_year.set_current", actions)

    def test_tenant_isolation(self):
        # Create an audit log for School B directly
        log_action(
            actor=self.principal_b,
            school=self.school_b,
            action="academic_year.create",
            changes={"note": "School B log"},
        )

        # Principal A checks audit logs
        self.client.force_authenticate(user=self.principal_a)
        res = self.client.get("/api/v1/audit/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Principal A sees zero records from School B
        school_ids = [entry["schoolId"] for entry in res.data]
        self.assertNotIn(self.school_b.id, school_ids)

        # Superuser can see School B logs or filter by ?school=
        self.client.force_authenticate(user=self.superuser)
        res_su = self.client.get(f"/api/v1/audit/?school={self.school_b.id}")
        self.assertEqual(res_su.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_su.data), 1)
        self.assertEqual(res_su.data[0]["schoolId"], self.school_b.id)

    def test_nobody_can_modify_or_delete_through_api(self):
        self.client.force_authenticate(user=self.superuser)
        res_post = self.client.post("/api/v1/audit/", data={"action": "fake"}, format="json")
        self.assertEqual(res_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        res_put = self.client.put("/api/v1/audit/", data={"action": "fake"}, format="json")
        self.assertEqual(res_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        res_delete = self.client.delete("/api/v1/audit/")
        self.assertEqual(res_delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_non_principal_roles_get_403(self):
        for user in [self.teacher_user, self.student_user, self.parent_user]:
            self.client.force_authenticate(user=user)
            res = self.client.get("/api/v1/audit/")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, f"{user.role} should be 403")

    def test_action_filter_and_limit(self):
        # Create multiple logs for School A
        log_action(actor=self.principal_a, school=self.school_a, action="notice.create")
        log_action(actor=self.principal_a, school=self.school_a, action="attendance.create")

        self.client.force_authenticate(user=self.principal_a)
        res = self.client.get("/api/v1/audit/?action=notice.create")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for item in res.data:
            self.assertEqual(item["action"], "notice.create")
