from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from academics.models import SchoolClass, Student, Subject, Teacher
from accounts.models import User
from schools.models import School


class ApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # School A and Principal A
        self.school_a = School.objects.create(name="School A", code="SCH-A", address="Road A", city="Indore")
        self.principal_a = User.objects.create_user(
            username="principal_a",
            password="Password@123",
            role="principal",
            first_name="Rakesh",
            last_name="Verma",
        )
        self.school_a.principal = self.principal_a
        self.school_a.save()

        # Teacher A in School A
        self.teacher_user_a = User.objects.create_user(
            username="teacher_a",
            password="Password@123",
            role="teacher",
            first_name="Neha",
            last_name="Joshi",
        )
        self.teacher_a = Teacher.objects.create(
            user=self.teacher_user_a,
            school=self.school_a,
            employee_id="T001",
        )
        self.class_a = SchoolClass.objects.create(
            name="10",
            section="A",
            school=self.school_a,
            class_teacher=self.teacher_a,
        )
        self.student_user_a = User.objects.create_user(
            username="student_a",
            password="Password@123",
            role="student",
            first_name="Aarav",
            last_name="Sharma",
        )
        self.student_a = Student.objects.create(
            user=self.student_user_a,
            school=self.school_a,
            class_section=self.class_a,
            admission_number="A001",
        )
        self.subject_a = Subject.objects.create(
            school=self.school_a,
            name="Mathematics",
            code="MATH10",
        )

        # School B and Principal B
        self.school_b = School.objects.create(name="School B", code="SCH-B", address="Road B", city="Bhopal")
        self.principal_b = User.objects.create_user(
            username="principal_b",
            password="Password@123",
            role="principal",
            first_name="Sanjay",
            last_name="Mehta",
        )
        self.school_b.principal = self.principal_b
        self.school_b.save()

        # Teacher B and Student B in School B
        self.teacher_user_b = User.objects.create_user(
            username="teacher_b",
            password="Password@123",
            role="teacher",
            first_name="Vikram",
            last_name="Singh",
        )
        self.teacher_b = Teacher.objects.create(
            user=self.teacher_user_b,
            school=self.school_b,
            employee_id="T002",
        )
        self.class_b = SchoolClass.objects.create(
            name="12",
            section="B",
            school=self.school_b,
            class_teacher=self.teacher_b,
        )
        self.student_user_b = User.objects.create_user(
            username="student_b",
            password="Password@123",
            role="student",
            first_name="Rohan",
            last_name="Gupta",
        )
        self.student_b = Student.objects.create(
            user=self.student_user_b,
            school=self.school_b,
            class_section=self.class_b,
            admission_number="B001",
        )

    def test_public_schools_list_anonymous(self):
        res = self.client.get("/api/v1/schools/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 2)

        res_detail = self.client.get(f"/api/v1/schools/{self.school_a.id}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data["name"], "School A")

    def test_auth_csrf(self):
        res = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("csrfToken", res.data)

    def test_login_success_and_failure(self):
        # Failure
        fail_res = self.client.post("/api/v1/auth/login/", {"username": "principal_a", "password": "wrong"})
        self.assertEqual(fail_res.status_code, status.HTTP_400_BAD_REQUEST)

        # Success
        ok_res = self.client.post("/api/v1/auth/login/", {"username": "principal_a", "password": "Password@123"})
        self.assertEqual(ok_res.status_code, status.HTTP_200_OK)
        self.assertEqual(ok_res.data["user"]["username"], "principal_a")
        self.assertEqual(ok_res.data["redirectUrl"], "/admin")

    def test_unauthenticated_me_returns_403(self):
        res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_principal_tenant_isolation(self):
        # Log in as Principal A
        self.client.force_login(self.principal_a)

        # Stats should only count School A
        stats_res = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(stats_res.status_code, status.HTTP_200_OK)
        self.assertEqual(stats_res.data["totalStudents"], 1)
        self.assertEqual(stats_res.data["totalTeachers"], 1)
        self.assertEqual(stats_res.data["totalClasses"], 1)

        # Classes should only return School A's classes
        classes_res = self.client.get("/api/v1/academics/classes/")
        self.assertEqual(classes_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(classes_res.data), 1)
        self.assertEqual(classes_res.data[0]["name"], "10")

        # Students should only return School A's students
        students_res = self.client.get("/api/v1/academics/students/")
        self.assertEqual(students_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(students_res.data), 1)
        self.assertEqual(students_res.data[0]["admissionNumber"], "A001")

        # Teachers should only return School A's teachers
        teachers_res = self.client.get("/api/v1/academics/teachers/")
        self.assertEqual(teachers_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(teachers_res.data), 1)
        self.assertEqual(teachers_res.data[0]["employeeId"], "T001")

    def test_teacher_sees_only_own_class_students(self):
        # Non-teacher gets 403 on my-students
        self.client.force_login(self.student_user_a)
        res = self.client.get("/api/v1/teacher/my-students/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Teacher A gets only their students
        self.client.force_login(self.teacher_user_a)
        t_res = self.client.get("/api/v1/teacher/my-students/")
        self.assertEqual(t_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(t_res.data["classes"]), 1)
        self.assertEqual(len(t_res.data["students"]), 1)
        self.assertEqual(t_res.data["students"][0]["admissionNumber"], "A001")
