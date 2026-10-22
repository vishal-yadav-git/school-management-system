from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from academics.models import SchoolClass, Student, Subject, Teacher
from accounts.models import User
from academic_year.models import AcademicYear
from attendance.models import AttendanceRecord, AttendanceSession
from guardians.models import Guardian
from organizations.models import Organization, OrganizationMember, SchoolOrganization
from schools.models import School
from teacher_assignments.models import ClassSubjectTeacher, TeacherPermission
from teacher_assignments.services import assign_class_subject_teacher, grant_permission


class Wave3BackendTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()

        # School A
        self.school_a = School.objects.create(name="School A", code="SCHA-09", address="Road A", city="Indore")
        self.principal_a = User.objects.create_user(
            username="principal_a",
            password="Password@123",
            role="principal",
            first_name="Rakesh",
            last_name="Verma",
        )
        self.school_a.principal = self.principal_a
        self.school_a.save()

        # School B
        self.school_b = School.objects.create(name="School B", code="SCHB-09", address="Road B", city="Indore")
        self.principal_b = User.objects.create_user(
            username="principal_b",
            password="Password@123",
            role="principal",
        )
        self.school_b.principal = self.principal_b
        self.school_b.save()

        # Academic Year for School A
        self.ay_a = AcademicYear.objects.create(
            school=self.school_a,
            name="2024-2025",
            start_date="2024-06-01",
            end_date="2025-04-30",
            is_current=True,
        )

        # Classes in School A
        self.class_10a = SchoolClass.objects.create(name="10", section="A", school=self.school_a)
        self.class_10b = SchoolClass.objects.create(name="10", section="B", school=self.school_a)

        # Teacher in School A
        self.teacher_user = User.objects.create_user(
            username="teacher_1",
            password="Password@123",
            role="teacher",
            first_name="Anita",
            last_name="Deshmukh",
        )
        self.teacher = Teacher.objects.create(user=self.teacher_user, school=self.school_a, employee_id="T01")

        # Assign Class Teacher of 10-A
        self.class_10a.class_teacher = self.teacher
        self.class_10a.save()

        # Subjects
        self.subject_math = Subject.objects.create(name="Mathematics", code="MATH10", school=self.school_a)
        self.subject_sci = Subject.objects.create(name="Science", code="SCI10", school=self.school_a)

        # Assign Subject Teacher of Math for 10-B
        self.cst = assign_class_subject_teacher(
            school=self.school_a,
            school_class=self.class_10b,
            subject=self.subject_math,
            teacher=self.teacher,
            actor=self.principal_a,
        )

        # Students in 10-A
        self.student_user_1 = User.objects.create_user(username="student_1", password="Password@123", role="student")
        self.student_1 = Student.objects.create(
            user=self.student_user_1,
            school=self.school_a,
            class_section=self.class_10a,
            admission_number="ADM001",
        )
        self.student_user_2 = User.objects.create_user(username="student_2", password="Password@123", role="student")
        self.student_2 = Student.objects.create(
            user=self.student_user_2,
            school=self.school_a,
            class_section=self.class_10a,
            admission_number="ADM002",
        )

        # Student in School B (to test isolation)
        self.student_user_b = User.objects.create_user(username="student_b", password="Password@123", role="student")
        self.student_b = Student.objects.create(
            user=self.student_user_b,
            school=self.school_b,
            admission_number="ADMB01",
        )

        # Superuser
        self.superuser = User.objects.create_superuser(username="root_admin", password="Password@123", email="root@indore.edu")

    def test_dashboard_summary_tenant_isolation(self):
        """School A principal only sees School A stats and 'not_taken_yet' attendance state."""
        self.client.force_authenticate(user=self.principal_a)
        res = self.client.get("/api/v1/dashboard/summary/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.assertEqual(res.data["school"]["id"], self.school_a.id)
        self.assertEqual(res.data["totalStudents"], 2)  # School B student excluded!
        self.assertEqual(res.data["totalTeachers"], 1)
        self.assertEqual(res.data["classesTotal"], 2)
        self.assertEqual(res.data["classesTaken"], 0)
        self.assertEqual(res.data["classesNotTaken"], 2)
        self.assertEqual(res.data["currentAcademicYear"]["name"], "2024-2025")

        # Plan Addition C: When no class taken today: taken=false, percent=null
        att = res.data["presentToday"]
        self.assertFalse(att["taken"])
        self.assertIsNone(att["percent"])

    def test_dashboard_summary_attendance_marked(self):
        """When attendance is recorded, summary aggregates presentToday percent and marked counts."""
        today = timezone.localdate()
        session = AttendanceSession.objects.create(
            school=self.school_a,
            school_class=self.class_10a,
            academic_year=self.ay_a,
            date=today,
            taken_by=self.teacher_user,
        )
        AttendanceRecord.objects.create(session=session, student=self.student_1, status="present")
        AttendanceRecord.objects.create(session=session, student=self.student_2, status="absent")

        self.client.force_authenticate(user=self.principal_a)
        res = self.client.get("/api/v1/dashboard/summary/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.assertEqual(res.data["classesTotal"], 2)
        self.assertEqual(res.data["classesTaken"], 1)
        self.assertEqual(res.data["classesNotTaken"], 1)

        att = res.data["presentToday"]
        self.assertTrue(att["taken"])
        self.assertEqual(att["percent"], 50.0)

    def test_dashboard_summary_query_count_no_n_plus_one(self):
        """
        Query count assertion on dashboard/summary:
        Asserts that response is generated via direct aggregate/count queries without N+1.
        """
        # Add 5 more classes and 10 more students to School A
        for i in range(5):
            c = SchoolClass.objects.create(name=f"Class{i}", section="A", school=self.school_a)
            for j in range(2):
                u = User.objects.create_user(username=f"stu_{i}_{j}", password="Password@123", role="student")
                Student.objects.create(user=u, school=self.school_a, class_section=c, admission_number=f"ADM_{i}_{j}")

        self.client.force_authenticate(user=self.principal_a)
        # Even with many classes and students, total queries is strictly bounded (< 12)
        with self.assertNumQueries(8):
            res = self.client.get("/api/v1/dashboard/summary/")
            self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_dashboard_summary_active_campus_from_session(self):
        """Org owner with campus switcher gets the switched campus summary."""
        admin_user = User.objects.create_user(username="org_owner", password="Password@123", role="admin")
        org = Organization.objects.create(name="Apex Group", code="APEX-09", owner=admin_user)
        OrganizationMember.objects.create(organization=org, user=admin_user, role="owner")
        SchoolOrganization.objects.create(school=self.school_a, organization=org, status="active", is_main_campus=True)
        SchoolOrganization.objects.create(school=self.school_b, organization=org, status="active", is_main_campus=False)

        self.client.force_authenticate(user=admin_user)
        # Default active campus is School A
        res = self.client.get("/api/v1/dashboard/summary/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["school"]["id"], self.school_a.id)

        # Switch campus to School B via session
        session = self.client.session
        session["active_school_id"] = self.school_b.id
        session.save()

        res2 = self.client.get("/api/v1/dashboard/summary/")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data["school"]["id"], self.school_b.id)
        self.assertEqual(res2.data["totalStudents"], 1)

    def test_dashboard_summary_forbidden_for_teacher_and_student(self):
        """Only principal/admin/superuser can access dashboard summary."""
        self.client.force_authenticate(user=self.teacher_user)
        res = self.client.get("/api/v1/dashboard/summary/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.student_user_1)
        res = self.client.get("/api/v1/dashboard/summary/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_my_classes_combines_class_and_subject_assignments(self):
        """
        Plan Addition A: Teacher receives both Class Teacher and Subject Teacher classes.
        role and canMarkAttendance are strictly enforced.
        """
        self.client.force_authenticate(user=self.teacher_user)
        res = self.client.get("/api/v1/teacher/my-classes/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        classes = res.data["classes"]
        self.assertEqual(len(classes), 2)

        c_10a = next(c for c in classes if c["id"] == self.class_10a.id)
        self.assertEqual(c_10a["role"], "class_teacher")
        self.assertTrue(c_10a["isClassTeacher"])
        self.assertTrue(c_10a["canMarkAttendance"])

        c_10b = next(c for c in classes if c["id"] == self.class_10b.id)
        self.assertEqual(c_10b["role"], "subject_teacher")
        self.assertFalse(c_10b["isClassTeacher"])
        self.assertFalse(c_10b["canMarkAttendance"])  # Strictly False per Plan Addition A!
        self.assertEqual(len(c_10b["subjects"]), 1)
        self.assertEqual(c_10b["subjects"][0]["code"], "MATH10")

    def test_teacher_my_classes_permissions_and_bounds(self):
        """
        Plan Addition B: Returns active academic year bounds and teacher permissions.
        """
        grant_permission(
            school=self.school_a,
            teacher=self.teacher,
            permission_key="attendance_backdate",
            actor=self.principal_a,
        )

        self.client.force_authenticate(user=self.teacher_user)
        res = self.client.get("/api/v1/teacher/my-classes/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.assertIn("attendance_backdate", res.data["permissions"])
        self.assertIsNotNone(res.data["currentAcademicYear"])
        self.assertEqual(res.data["currentAcademicYear"]["startDate"], "2024-06-01")
        self.assertEqual(res.data["currentAcademicYear"]["endDate"], "2025-04-30")

    def test_teacher_my_classes_forbidden_for_non_teachers(self):
        """Students and parents cannot access teacher my-classes endpoint."""
        self.client.force_authenticate(user=self.student_user_1)
        res = self.client.get("/api/v1/teacher/my-classes/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_class_subject_teacher_delete_principal_only(self):
        """Principal can delete a subject teacher mapping; logs audit."""
        self.client.force_authenticate(user=self.principal_a)
        res = self.client.delete(f"/api/v1/classes/{self.class_10b.id}/subject-teachers/{self.cst.id}/")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        # Verify mapping is deleted
        self.assertFalse(ClassSubjectTeacher.objects.filter(id=self.cst.id).exists())

        # Non-principal receives 403
        self.client.force_authenticate(user=self.teacher_user)
        res2 = self.client.delete(f"/api/v1/classes/{self.class_10b.id}/subject-teachers/999/")
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)
