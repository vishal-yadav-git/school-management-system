from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from schools.models import School
from .models import AcademicYear


class AcademicYearTests(TestCase):
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

    def test_principal_can_list_and_create_academic_year(self):
        self.client.force_authenticate(user=self.principal_a)
        payload = {
            "name": "2026-27",
            "startDate": "2026-04-01",
            "endDate": "2027-03-31",
            "isCurrent": True,
        }
        res = self.client.post("/api/v1/academic-years/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["name"], "2026-27")
        self.assertEqual(res.data["isCurrent"], True)
        self.assertEqual(res.data["schoolId"], self.school_a.id)

        # GET should return it
        res_get = self.client.get("/api/v1/academic-years/")
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_get.data), 1)
        self.assertEqual(res_get.data[0]["name"], "2026-27")

    def test_tenant_isolation_principal_cannot_list_or_create_for_school_b(self):
        # Create year in School B directly
        ay_b = AcademicYear.objects.create(
            school=self.school_b,
            name="2026-27",
            start_date="2026-04-01",
            end_date="2027-03-31",
            is_current=True,
        )

        # Principal A logs in
        self.client.force_authenticate(user=self.principal_a)

        # GET academic-years/ (even with ?school=B) returns only School A's records (0 records)
        res = self.client.get(f"/api/v1/academic-years/?school={self.school_b.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 0)

        # Principal A tries to POST for School B
        payload = {
            "school": self.school_b.id,
            "name": "2027-28",
            "startDate": "2027-04-01",
            "endDate": "2028-03-31",
            "isCurrent": False,
        }
        res_post = self.client.post("/api/v1/academic-years/", data=payload, format="json")
        self.assertEqual(res_post.status_code, status.HTTP_201_CREATED)
        # Verify it was saved under School A, NOT School B
        created = AcademicYear.objects.get(name="2027-28")
        self.assertEqual(created.school, self.school_a)
        self.assertNotEqual(created.school, self.school_b)

    def test_one_current_year_per_school_enforced(self):
        self.client.force_authenticate(user=self.principal_a)

        # Create Year 1 as current
        res1 = self.client.post(
            "/api/v1/academic-years/",
            data={"name": "2025-26", "startDate": "2025-04-01", "endDate": "2026-03-31", "isCurrent": True},
            format="json",
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        ay1_id = res1.data["id"]

        # Create Year 2 as current
        res2 = self.client.post(
            "/api/v1/academic-years/",
            data={"name": "2026-27", "startDate": "2026-04-01", "endDate": "2027-03-31", "isCurrent": True},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        ay2_id = res2.data["id"]

        # In DB: ay1 should now be is_current=False, ay2 should be is_current=True
        ay1 = AcademicYear.objects.get(id=ay1_id)
        ay2 = AcademicYear.objects.get(id=ay2_id)
        self.assertFalse(ay1.is_current)
        self.assertTrue(ay2.is_current)

        # Verify DB constraint prevents two current years for the same school
        with self.assertRaises(IntegrityError):
            AcademicYear.objects.create(
                school=self.school_a,
                name="2027-28",
                start_date="2027-04-01",
                end_date="2028-03-31",
                is_current=True,
            )

    def test_end_date_after_start_date(self):
        self.client.force_authenticate(user=self.principal_a)

        # End date before start date
        res = self.client.post(
            "/api/v1/academic-years/",
            data={"name": "Bad-1", "startDate": "2026-04-01", "endDate": "2026-03-01", "isCurrent": False},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("endDate", res.data)

        # End date equal to start date
        res2 = self.client.post(
            "/api/v1/academic-years/",
            data={"name": "Bad-2", "startDate": "2026-04-01", "endDate": "2026-04-01", "isCurrent": False},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("endDate", res2.data)

    def test_teacher_parent_student_get_403(self):
        for user in [self.teacher_user, self.student_user, self.parent_user]:
            self.client.force_authenticate(user=user)
            res_get = self.client.get("/api/v1/academic-years/")
            self.assertEqual(res_get.status_code, status.HTTP_403_FORBIDDEN, f"{user.role} should be 403 on GET")
            res_post = self.client.post(
                "/api/v1/academic-years/",
                data={"name": "2026-27", "startDate": "2026-04-01", "endDate": "2027-03-31"},
                format="json",
            )
            self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN, f"{user.role} should be 403 on POST")
