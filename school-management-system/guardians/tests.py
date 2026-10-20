from django.core.cache import cache
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from academics.models import SchoolClass, Student
from accounts.models import User
from audit.models import AuditLog
from guardians.models import Guardian, StudentGuardian
from schools.models import School


class GuardianTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

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

        # Class and Student in School A
        self.class_a = SchoolClass.objects.create(name="10", section="A", school=self.school_a)
        self.student_user_1 = User.objects.create_user(username="student1", role="student", first_name="Aarav", last_name="Sharma")
        self.student_1 = Student.objects.create(
            user=self.student_user_1,
            school=self.school_a,
            class_section=self.class_a,
            admission_number="SCH-A-001",
        )

        # Sibling student in School A
        self.student_user_2 = User.objects.create_user(username="student2", role="student", first_name="Ananya", last_name="Sharma")
        self.student_2 = Student.objects.create(
            user=self.student_user_2,
            school=self.school_a,
            class_section=self.class_a,
            admission_number="SCH-A-002",
        )

        # Student in School B
        self.student_user_b = User.objects.create_user(username="student_b", role="student", first_name="Rohan", last_name="Mehta")
        self.student_b = Student.objects.create(
            user=self.student_user_b,
            school=self.school_b,
            admission_number="SCH-B-001",
        )

        # Parent User with mobile
        self.parent_user = User.objects.create_user(
            username="parent_user",
            password="Password@123",
            role="parent",
            mobile="+91 98260 12345",
            first_name="Suresh",
            last_name="Sharma",
        )

        # Parent User with empty mobile
        self.empty_mobile_parent = User.objects.create_user(
            username="parent_empty",
            password="Password@123",
            role="parent",
            mobile="",
        )

    def test_principal_add_and_list_guardian(self):
        self.client.force_authenticate(user=self.principal_a)

        # Add father as primary
        res = self.client.post(
            f"/api/v1/students/{self.student_1.id}/guardians/",
            data={
                "fullName": "Suresh Sharma",
                "mobile": "9826012345",
                "relation": "father",
                "isPrimary": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["fullName"], "Suresh Sharma")
        self.assertEqual(res.data["mobile"], "9826012345")
        self.assertTrue(res.data["isPrimary"])

        # GET guardians for student 1
        res_get = self.client.get(f"/api/v1/students/{self.student_1.id}/guardians/")
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_get.data), 1)

        # Verify audit log was written
        audit = AuditLog.objects.filter(school=self.school_a, action="guardian.add")
        self.assertEqual(audit.count(), 1)

    def test_sibling_guardian_reuse(self):
        self.client.force_authenticate(user=self.principal_a)

        # Add guardian to student 1
        self.client.post(
            f"/api/v1/students/{self.student_1.id}/guardians/",
            data={"fullName": "Suresh Sharma", "mobile": "9826012345", "relation": "father"},
            format="json",
        )

        # Add same mobile to sibling (student 2)
        self.client.post(
            f"/api/v1/students/{self.student_2.id}/guardians/",
            data={"fullName": "Suresh Sharma", "mobile": "9826012345", "relation": "father"},
            format="json",
        )

        # Verify only 1 Guardian row was created in School A
        self.assertEqual(Guardian.objects.filter(school=self.school_a).count(), 1)
        # But 2 StudentGuardian links exist
        self.assertEqual(StudentGuardian.objects.count(), 2)

    def test_tenant_isolation_principal_cannot_access_other_school_students(self):
        self.client.force_authenticate(user=self.principal_a)

        # Try to view student B's guardians
        res = self.client.get(f"/api/v1/students/{self.student_b.id}/guardians/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Try to add guardian to student B
        res_add = self.client.post(
            f"/api/v1/students/{self.student_b.id}/guardians/",
            data={"fullName": "Fake", "mobile": "9999999999"},
            format="json",
        )
        self.assertEqual(res_add.status_code, status.HTTP_403_FORBIDDEN)

    def test_claim_flow_and_approval(self):
        # 1. Principal adds guardian with 10 digits
        self.client.force_authenticate(user=self.principal_a)
        res_add = self.client.post(
            f"/api/v1/students/{self.student_1.id}/guardians/",
            data={"fullName": "Suresh Sharma", "mobile": "9826012345", "relation": "father"},
            format="json",
        )
        guardian_id = res_add.data["guardianId"]

        # 2. Parent with empty mobile attempts to claim -> 400
        self.client.force_authenticate(user=self.empty_mobile_parent)
        res_empty = self.client.post("/api/v1/guardians/claim/", data={"mobile": "9826012345"}, format="json")
        self.assertEqual(res_empty.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_empty.data["detail"], "Add your mobile number to your account first.")

        # 3. Parent with matching mobile claims (body mobile ignored)
        self.client.force_authenticate(user=self.parent_user)
        res_claim = self.client.post("/api/v1/guardians/claim/", data={"mobile": "0000000000"}, format="json")
        self.assertEqual(res_claim.status_code, status.HTTP_200_OK)
        self.assertEqual(res_claim.data["pendingCount"], 1)
        self.assertIn("School A", res_claim.data["matchedSchools"])

        # Check guardian status is pending, not approved yet
        g = Guardian.objects.get(id=guardian_id)
        self.assertEqual(g.link_status, "pending")
        self.assertEqual(g.requested_user, self.parent_user)
        self.assertIsNone(g.user)

        # Parent checks children -> 0 because pending
        res_kids = self.client.get("/api/v1/parent/children/")
        self.assertEqual(len(res_kids.data), 0)

        # 4. Principal lists pending requests
        self.client.force_authenticate(user=self.principal_a)
        res_reqs = self.client.get("/api/v1/guardians/link-requests/")
        self.assertEqual(res_reqs.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_reqs.data), 1)
        self.assertEqual(res_reqs.data[0]["id"], guardian_id)

        # 5. Principal approves
        res_app = self.client.post(f"/api/v1/guardians/link-requests/{guardian_id}/approve/")
        self.assertEqual(res_app.status_code, status.HTTP_200_OK)

        g.refresh_from_db()
        self.assertEqual(g.link_status, "approved")
        self.assertEqual(g.user, self.parent_user)

        # 6. Parent checks children -> student 1 is now visible!
        self.client.force_authenticate(user=self.parent_user)
        res_kids = self.client.get("/api/v1/parent/children/")
        self.assertEqual(res_kids.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_kids.data), 1)
        self.assertEqual(res_kids.data[0]["name"], "Aarav Sharma")
        self.assertEqual(res_kids.data[0]["schoolName"], "School A")
