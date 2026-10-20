from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from academics.models import SchoolClass, Student, Subject, Teacher
from accounts.models import User
from schools.models import School


class ApiTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()

        # Superuser
        self.superuser = User.objects.create_superuser(
            username="admin_root",
            password="Password@123",
            email="admin@indore.edu",
        )

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

    def test_parent_register_success_and_role_hardcoded(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "parent_new",
                "password": "SecurePassword@123!",
                "fullName": "Sunita Verma",
                "mobile": "9826012345",
                "email": "sunita@example.com",
                "role": "parent",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["user"]["role"], "parent")
        self.assertEqual(res.data["redirectUrl"], "/parent")
        self.assertTrue(self.client.session.get("_auth_user_id"))

        user = User.objects.get(username="parent_new")
        self.assertEqual(user.role, "parent")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_parent_register_ignores_role_tampering(self):
        res_admin = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "tamper_user",
                "password": "SecurePassword@123!",
                "role": "admin",
            },
        )
        self.assertEqual(res_admin.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", res_admin.data)

        res_principal = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "tamper_principal",
                "password": "SecurePassword@123!",
                "role": "principal",
            },
        )
        self.assertEqual(res_principal.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", res_principal.data)

    def test_register_admin_role_rejected(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {"username": "fake_admin", "password": "SecurePassword@123!", "role": "admin"},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", res.data)

    def test_register_principal_role_rejected(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {"username": "fake_principal", "password": "SecurePassword@123!", "role": "principal"},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", res.data)

    def test_register_student_success(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "new_student_reg",
                "password": "SecurePassword@123!",
                "firstName": "Priya",
                "lastName": "Patel",
                "role": "student",
                "schoolId": self.school_a.id,
                "admissionNumber": "ADM-NEW-001",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["user"]["role"], "student")
        self.assertEqual(res.data["redirectUrl"], "/student")
        self.assertTrue(self.client.session.get("_auth_user_id"))
        self.assertIn("student", res.data)
        self.assertEqual(res.data["student"]["admissionNumber"], "ADM-NEW-001")
        self.assertIsNone(res.data["student"]["className"])
        from academics.models import Student
        self.assertTrue(Student.objects.filter(admission_number="ADM-NEW-001").exists())

    def test_student_session_payload_contains_admission_and_class_name(self):
        self.client.force_login(self.student_user_a)
        res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["redirectUrl"], "/student")
        self.assertIn("student", res.data)
        self.assertEqual(res.data["student"]["admissionNumber"], "A001")
        self.assertEqual(res.data["student"]["className"], "10-A")

    def test_register_teacher_success(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "new_teacher_reg",
                "password": "SecurePassword@123!",
                "firstName": "Deepak",
                "lastName": "Jain",
                "role": "teacher",
                "schoolId": self.school_a.id,
                "employeeId": "EMP-NEW-001",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["user"]["role"], "teacher")
        self.assertEqual(res.data["redirectUrl"], "/teacher/attendance")
        self.assertTrue(self.client.session.get("_auth_user_id"))
        from academics.models import Teacher
        self.assertTrue(Teacher.objects.filter(employee_id="EMP-NEW-001").exists())

    def test_register_student_missing_school_rejected(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "student_no_school",
                "password": "SecurePassword@123!",
                "role": "student",
                "admissionNumber": "ADM-NOSCH",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("schoolId", res.data)

    def test_register_student_unknown_school_rejected(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "student_bad_school",
                "password": "SecurePassword@123!",
                "role": "student",
                "schoolId": 999999,
                "admissionNumber": "ADM-NOSCH-99",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("schoolId", res.data)

    def test_register_student_missing_admission_number_rejected(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "student_no_adm",
                "password": "SecurePassword@123!",
                "role": "student",
                "schoolId": self.school_a.id,
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("admissionNumber", res.data)

    def test_register_teacher_missing_employee_id_rejected(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "teacher_no_emp",
                "password": "SecurePassword@123!",
                "role": "teacher",
                "schoolId": self.school_a.id,
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("employeeId", res.data)

    def test_register_teacher_duplicate_employee_id_rejected(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "teacher_dup_emp",
                "password": "SecurePassword@123!",
                "role": "teacher",
                "schoolId": self.school_a.id,
                "employeeId": "T001",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("employeeId", res.data)

    def test_register_student_duplicate_admission_number_rejected(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "student_dup_adm",
                "password": "SecurePassword@123!",
                "role": "student",
                "schoolId": self.school_a.id,
                "admissionNumber": "A001",  # already exists
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("admissionNumber", res.data)

    def test_register_duplicate_username_case_insensitive_rejected(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "PRINCIPAL_A",  # existing is principal_a
                "password": "SecurePassword@123!",
                "role": "parent",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", res.data)

    def test_register_atomic_rollback_on_failed_profile(self):
        # Attempt to register student with duplicate admissionNumber
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "orphan_check_user",
                "password": "SecurePassword@123!",
                "role": "student",
                "schoolId": self.school_a.id,
                "admissionNumber": "A001",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        # Verify no orphan User was created
        self.assertFalse(User.objects.filter(username="orphan_check_user").exists())

    def test_newly_registered_student_and_teacher_isolation(self):
        # Register student
        res_s = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "iso_student",
                "password": "SecurePassword@123!",
                "role": "student",
                "schoolId": self.school_a.id,
                "admissionNumber": "ISO-001",
            },
        )
        self.assertEqual(res_s.status_code, status.HTTP_201_CREATED)
        # Student gets 403 on admin/dashboard and academics
        res_dash = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(res_dash.status_code, status.HTTP_403_FORBIDDEN)
        res_classes = self.client.get("/api/v1/academics/classes/")
        self.assertEqual(res_classes.status_code, status.HTTP_403_FORBIDDEN)

        # Register teacher
        res_t = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "iso_teacher",
                "password": "SecurePassword@123!",
                "role": "teacher",
                "schoolId": self.school_a.id,
                "employeeId": "ISO-T01",
            },
        )
        self.assertEqual(res_t.status_code, status.HTTP_201_CREATED)
        # Teacher gets empty list from my-students
        res_students = self.client.get("/api/v1/teacher/my-students/")
        self.assertEqual(res_students.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_students.data["students"]), 0)

    def test_login_registered_user_success_and_failure(self):
        # Register a parent
        self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "reg_parent_login",
                "password": "SecurePassword@123!",
                "role": "parent",
            },
        )
        self.client.logout()

        # Login wrong password -> 400
        res_fail = self.client.post(
            "/api/v1/auth/login/",
            {"username": "reg_parent_login", "password": "WrongPassword"},
        )
        self.assertEqual(res_fail.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_fail.data["detail"], "Invalid username or password")

        # Login correct password -> 200
        res_ok = self.client.post(
            "/api/v1/auth/login/",
            {"username": "reg_parent_login", "password": "SecurePassword@123!"},
        )
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)
        self.assertEqual(res_ok.data["user"]["username"], "reg_parent_login")
        self.assertEqual(res_ok.data["redirectUrl"], "/parent")

    def test_register_prevents_is_staff_and_is_superuser_escalation(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "escalate_user",
                "password": "SecurePassword@123!",
                "role": "parent",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="escalate_user")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_parent_register_weak_password_rejected(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "weak_pwd_user",
                "password": "123",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", res.data)

    def test_parent_register_duplicate_username_rejected(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "principal_a",
                "password": "SecurePassword@123!",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", res.data)

    def test_user_register_with_name_email_mobile_and_login_by_email_or_mobile(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "name": "Aman Sharma",
                "email": "aman.sharma@example.com",
                "mobile": "9876543210",
                "password": "SecurePassword@123!",
                "role": "parent",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["user"]["email"], "aman.sharma@example.com")
        self.assertEqual(res.data["user"]["mobile"], "9876543210")
        self.assertEqual(res.data["user"]["firstName"], "Aman")
        self.assertEqual(res.data["user"]["lastName"], "Sharma")
        self.client.logout()

        # Login with email
        res_email = self.client.post(
            "/api/v1/auth/login/",
            {"username": "aman.sharma@example.com", "password": "SecurePassword@123!"},
        )
        self.assertEqual(res_email.status_code, status.HTTP_200_OK)
        self.client.logout()

        # Login with mobile
        res_mobile = self.client.post(
            "/api/v1/auth/login/",
            {"username": "9876543210", "password": "SecurePassword@123!"},
        )
        self.assertEqual(res_mobile.status_code, status.HTTP_200_OK)

    def test_institute_admin_register_success(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "dean_renaissance",
                "email": "dean@renaissance.edu",
                "mobile": "9826012345",
                "instituteName": "Renaissance University Indore",
                "designation": "Campus Director",
                "password": "SecurePassword@123!",
                "role": "admin",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["user"]["role"], "admin")
        self.assertEqual(res.data["redirectUrl"], "/admin")
        self.assertIsNotNone(res.data["school"])
        self.assertEqual(res.data["school"]["name"], "Renaissance University Indore")
        from schools.models import School
        self.assertTrue(School.objects.filter(name="Renaissance University Indore").exists())

    def test_student_me_success_and_isolation(self):
        # Non-student gets 403
        self.client.force_login(self.teacher_user_a)
        res_teacher = self.client.get("/api/v1/student/me/")
        self.assertEqual(res_teacher.status_code, status.HTTP_403_FORBIDDEN)

        # Student A sees own profile
        self.client.force_login(self.student_user_a)
        res_a = self.client.get("/api/v1/student/me/")
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)
        self.assertEqual(res_a.data["admissionNumber"], "A001")
        self.assertEqual(res_a.data["name"], "Aarav Sharma")
        self.assertEqual(res_a.data["className"], "10-A")

        # Student B sees own profile
        self.client.force_login(self.student_user_b)
        res_b = self.client.get("/api/v1/student/me/")
        self.assertEqual(res_b.status_code, status.HTTP_200_OK)
        self.assertEqual(res_b.data["admissionNumber"], "B001")
        self.assertEqual(res_b.data["name"], "Rohan Gupta")

    def test_login_throttle_returns_429(self):
        from django.core.cache import cache
        cache.clear()

        # Anon throttle is 10/min
        throttled_client = APIClient()
        for _ in range(10):
            throttled_client.post("/api/v1/auth/login/", {"username": "bad", "password": "bad"})
        res = throttled_client.post("/api/v1/auth/login/", {"username": "bad", "password": "bad"})
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_login_remember_me_session_expiry(self):
        from django.core.cache import cache
        cache.clear()

        # Test remember=True (default or explicit)
        client_remember = APIClient()
        res_rem = client_remember.post("/api/v1/auth/login/", {
            "username": "principal_a",
            "password": "Password@123",
            "remember": True
        })
        self.assertEqual(res_rem.status_code, status.HTTP_200_OK)
        # Session expiry should be > 0 (14 days = 1209600s)
        self.assertEqual(client_remember.session.get_expiry_age(), 14 * 24 * 60 * 60)

        # Test remember=False (browser close, set_expiry(0))
        client_no_remember = APIClient()
        res_no_rem = client_no_remember.post("/api/v1/auth/login/", {
            "username": "principal_a",
            "password": "Password@123",
            "remember": False
        })
        self.assertEqual(res_no_rem.status_code, status.HTTP_200_OK)
        # In Django, set_expiry(0) means expire at browser close (get_expire_at_browser_close() is True)
        self.assertTrue(client_no_remember.session.get_expire_at_browser_close())

    def test_admin_classes_crud_and_cross_school_isolation(self):
        # Principal A lists classes (should only see Class A)
        self.client.force_login(self.principal_a)
        res = self.client.get("/api/v1/admin/classes/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["name"], "10")

        # Create new class in School A
        res_create = self.client.post("/api/v1/admin/classes/", {
            "name": "11",
            "section": "A",
            "classTeacher": self.teacher_a.id,
            "school": self.school_b.id, # Tampering attempt - should be ignored
        })
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_create.data["school"], self.school_a.id)
        class_id = res_create.data["id"]

        # Attempt to link Teacher B from School B to School A class -> 400
        res_bad_teacher = self.client.post("/api/v1/admin/classes/", {
            "name": "11",
            "section": "C",
            "classTeacher": self.teacher_b.id,
        })
        self.assertEqual(res_bad_teacher.status_code, status.HTTP_400_BAD_REQUEST)

        # Cross-school access: Principal A requests Class B from School B -> 404
        res_cross = self.client.get(f"/api/v1/admin/classes/{self.class_b.id}/")
        self.assertEqual(res_cross.status_code, status.HTTP_404_NOT_FOUND)

        # Delete Class A
        res_del = self.client.delete(f"/api/v1/admin/classes/{class_id}/")
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
        self.assertFalse(SchoolClass.objects.filter(id=class_id).exists())

    def test_admin_teachers_crud_and_credentials_returned(self):
        self.client.force_login(self.principal_a)

        # Create teacher
        res_create = self.client.post("/api/v1/admin/teachers/", {
            "firstName": "Anita",
            "lastName": "Deshmukh",
            "username": "anita_t",
            "email": "anita@schoola.ac.in",
            "mobile": "9876543210",
            "password": "Teacher@123",
            "employeeId": "EMP-999",
            "designation": "Senior Lecturer",
            "role": "admin", # Role tampering attempt - must stay teacher
        })
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertIn("generatedCredentials", res_create.data)
        self.assertEqual(res_create.data["generatedCredentials"]["username"], "anita_t")
        self.assertEqual(res_create.data["generatedCredentials"]["password"], "Teacher@123")
        self.assertEqual(res_create.data["school"], self.school_a.id)

        teacher_user = User.objects.get(username="anita_t")
        self.assertEqual(teacher_user.role, "teacher")

        teacher_id = res_create.data["id"]

        # Cross-school access: Principal A accessing Teacher B -> 404
        res_cross = self.client.get(f"/api/v1/admin/teachers/{self.teacher_b.id}/")
        self.assertEqual(res_cross.status_code, status.HTTP_404_NOT_FOUND)

        # Delete teacher cleans up User
        res_del = self.client.delete(f"/api/v1/admin/teachers/{teacher_id}/")
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
        self.assertFalse(Teacher.objects.filter(id=teacher_id).exists())
        self.assertFalse(User.objects.filter(username="anita_t").exists())

    def test_admin_students_crud_and_cross_school_isolation(self):
        self.client.force_login(self.principal_a)

        # Create Student
        res_create = self.client.post("/api/v1/admin/students/", {
            "firstName": "Kunal",
            "lastName": "Verma",
            "username": "kunal_v",
            "password": "Student@123",
            "admissionNumber": "ADM-888",
            "classSection": self.class_a.id,
            "gender": "Male",
            "school": self.school_b.id, # Tamper attempt
        })
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_create.data["school"], self.school_a.id)
        student_id = res_create.data["id"]

        # Cross-school access: Principal A requesting Student B -> 404
        res_cross = self.client.get(f"/api/v1/admin/students/{self.student_b.id}/")
        self.assertEqual(res_cross.status_code, status.HTTP_404_NOT_FOUND)

        # Delete student cleans up User
        res_del = self.client.delete(f"/api/v1/admin/students/{student_id}/")
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
        self.assertFalse(Student.objects.filter(id=student_id).exists())
        self.assertFalse(User.objects.filter(username="kunal_v").exists())

    def test_unauthorized_roles_blocked_from_admin_apis(self):
        # Teacher blocked
        self.client.force_login(self.teacher_user_a)
        res_teacher = self.client.get("/api/v1/admin/classes/")
        self.assertEqual(res_teacher.status_code, status.HTTP_403_FORBIDDEN)

        # Student blocked
        self.client.force_login(self.student_user_a)
        res_student = self.client.get("/api/v1/admin/students/")
        self.assertEqual(res_student.status_code, status.HTTP_403_FORBIDDEN)

        # Anonymous blocked
        self.client.logout()
        res_anon = self.client.get("/api/v1/admin/teachers/")
        self.assertEqual(res_anon.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_only_schools_and_principals(self):
        # Principal A forbidden from /admin/schools/
        self.client.force_login(self.principal_a)
        res_p_schools = self.client.get("/api/v1/admin/schools/")
        self.assertEqual(res_p_schools.status_code, status.HTTP_403_FORBIDDEN)

        # Superuser allowed
        self.client.force_login(self.superuser)
        res_su_schools = self.client.get("/api/v1/admin/schools/")
        self.assertEqual(res_su_schools.status_code, status.HTTP_200_OK)
        self.assertEqual(res_su_schools.data["count"], 2)

        # Superuser creates principal
        res_p_create = self.client.post("/api/v1/admin/principals/", {
            "username": "new_director",
            "password": "Password@123",
            "firstName": "Deepak",
            "lastName": "Joshi",
            "schoolId": self.school_a.id,
        })
        self.assertEqual(res_p_create.status_code, status.HTTP_201_CREATED)

    def test_import_preview_and_confirm_flow(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.principal_a)

        csv_content = (
            "Student ID,Student Name,Class,Section,Mobile No\n"
            "IMP-001,Amit Patel,10,A,9826012345\n"
            "IMP-002,Priya Shah,10,B,9826054321\n"
        ).encode("utf-8")
        uploaded = SimpleUploadedFile("students.csv", csv_content, content_type="text/csv")

        # Preview
        res_preview = self.client.post("/api/v1/admin/import/preview/", {"file": uploaded})
        self.assertEqual(res_preview.status_code, status.HTTP_200_OK)
        self.assertIn("importToken", res_preview.data)
        self.assertEqual(res_preview.data["totalRows"], 2)
        token = res_preview.data["importToken"]

        # Confirm
        res_confirm = self.client.post("/api/v1/admin/import/confirm/", {"importToken": token})
        self.assertEqual(res_confirm.status_code, status.HTTP_200_OK)
        self.assertEqual(res_confirm.data["imported"], 2)
        self.assertEqual(res_confirm.data["duplicate"], 0)

        # Verify created records
        self.assertTrue(Student.objects.filter(admission_number="IMP-001").exists())
        self.assertTrue(User.objects.filter(username=f"{self.school_a.code.lower()}_imp-001").exists())


