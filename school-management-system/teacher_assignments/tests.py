from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from academic_year.models import AcademicYear
from academics.models import SchoolClass, Student, Subject, Teacher
from accounts.models import User
from attendance.models import AttendanceSession
from audit.models import AuditLog
from schools.models import School
from teacher_assignments.models import ClassSubjectTeacher, TeacherPermission


class TeacherAssignmentsTests(APITestCase):
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

        # Academic year for attendance test
        today = timezone.localdate()
        self.ay = AcademicYear.objects.create(
            school=self.school_a,
            name="2026-2027",
            start_date=today - timedelta(days=60),
            end_date=today + timedelta(days=300),
            is_current=True,
        )

        self.teacher_user_1 = User.objects.create_user(
            username="teacher_1",
            email="t1@example.com",
            password="Password@123!",
            role="teacher",
            first_name="Ravi",
            last_name="Kumar",
        )
        self.teacher_1 = Teacher.objects.create(
            user=self.teacher_user_1,
            school=self.school_a,
            employee_id="EMP-T1",
        )

        self.teacher_user_2 = User.objects.create_user(
            username="teacher_2",
            email="t2@example.com",
            password="Password@123!",
            role="teacher",
            first_name="Sanjay",
            last_name="Mishra",
        )
        self.teacher_2 = Teacher.objects.create(
            user=self.teacher_user_2,
            school=self.school_a,
            employee_id="EMP-T2",
        )

        # Cross-school teacher
        self.teacher_user_b = User.objects.create_user(
            username="teacher_b",
            email="tb@example.com",
            password="Password@123!",
            role="teacher",
        )
        self.teacher_b = Teacher.objects.create(
            user=self.teacher_user_b,
            school=self.school_b,
            employee_id="EMP-TB",
        )

        self.school_class = SchoolClass.objects.create(
            school=self.school_a,
            name="10",
            section="A",
            class_teacher=self.teacher_1,
        )
        self.subject = Subject.objects.create(
            school=self.school_a,
            name="Mathematics",
            code="MATH10",
        )

        # Enrolled student for attendance tests
        self.student_user = User.objects.create_user(
            username="student_1",
            password="Password@123!",
            role="student",
        )
        self.student = Student.objects.create(
            user=self.student_user,
            school=self.school_a,
            class_section=self.school_class,
            admission_number="ADM-001",
        )

    def test_permission_keys_whitelist_rejects_unknown_keys(self):
        self.client.force_login(self.principal_a)

        res = self.client.post(
            f"/api/v1/teachers/{self.teacher_1.id}/permissions/",
            {"permissionKey": "invalid_super_key", "granted": True},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("permissionKey", res.data)

    def test_grant_and_revoke_permissions_log_audit_actions(self):
        self.client.force_login(self.principal_a)

        # Grant permission
        res_grant = self.client.post(
            f"/api/v1/teachers/{self.teacher_1.id}/permissions/",
            {"permissionKey": "manage_syllabus", "granted": True},
        )
        self.assertEqual(res_grant.status_code, status.HTTP_200_OK)
        self.assertTrue(TeacherPermission.objects.filter(teacher=self.teacher_1, permission_key="manage_syllabus").exists())

        audit_grant = AuditLog.objects.filter(action="permission.grant", school=self.school_a).first()
        self.assertIsNotNone(audit_grant)
        self.assertEqual(audit_grant.actor, self.principal_a)

        # Revoke permission
        res_revoke = self.client.post(
            f"/api/v1/teachers/{self.teacher_1.id}/permissions/",
            {"permissionKey": "manage_syllabus", "granted": False},
        )
        self.assertEqual(res_revoke.status_code, status.HTTP_200_OK)
        self.assertFalse(TeacherPermission.objects.filter(teacher=self.teacher_1, permission_key="manage_syllabus").exists())

        audit_revoke = AuditLog.objects.filter(action="permission.revoke", school=self.school_a).first()
        self.assertIsNotNone(audit_revoke)

    def test_teacher_with_attendance_backdate_can_submit_past_attendance(self):
        self.client.force_login(self.teacher_user_1)
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()

        payload = {
            "date": yesterday,
            "records": [{"studentId": self.student.id, "status": "present"}],
        }

        # 1. Before permission: teacher fails to take past attendance
        res_fail = self.client.put(f"/api/v1/attendance/class/{self.school_class.id}/", payload, format="json")
        self.assertEqual(res_fail.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Grant attendance_backdate permission
        TeacherPermission.objects.create(
            school=self.school_a,
            teacher=self.teacher_1,
            permission_key="attendance_backdate",
            granted_by=self.principal_a,
        )

        # 3. Now teacher successfully submits past attendance!
        res_success = self.client.put(f"/api/v1/attendance/class/{self.school_class.id}/", payload, format="json")
        self.assertEqual(res_success.status_code, status.HTTP_200_OK)
        self.assertTrue(AttendanceSession.objects.filter(school_class=self.school_class, date=yesterday).exists())

    def test_class_subject_teacher_enforces_one_teacher_per_subject(self):
        self.client.force_login(self.principal_a)

        # Assign teacher 1 to math
        res1 = self.client.post(
            f"/api/v1/classes/{self.school_class.id}/subject-teachers/",
            {"subjectId": self.subject.id, "teacherId": self.teacher_1.id},
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ClassSubjectTeacher.objects.filter(school_class=self.school_class, subject=self.subject).count(), 1)
        self.assertEqual(ClassSubjectTeacher.objects.get(school_class=self.school_class, subject=self.subject).teacher, self.teacher_1)

        # Re-assign same subject in same class to teacher 2 (should update cleanly, not duplicate)
        res2 = self.client.post(
            f"/api/v1/classes/{self.school_class.id}/subject-teachers/",
            {"subjectId": self.subject.id, "teacherId": self.teacher_2.id},
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ClassSubjectTeacher.objects.filter(school_class=self.school_class, subject=self.subject).count(), 1)
        self.assertEqual(ClassSubjectTeacher.objects.get(school_class=self.school_class, subject=self.subject).teacher, self.teacher_2)

    def test_cross_school_teacher_permission_rejected(self):
        self.client.force_login(self.principal_a)

        # Principal A tries to manage teacher B from school B
        res = self.client.post(
            f"/api/v1/teachers/{self.teacher_b.id}/permissions/",
            {"permissionKey": "publish_notices", "granted": True},
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
