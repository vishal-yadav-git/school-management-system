from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from academic_year.models import AcademicYear
from academics.models import SchoolClass, Student, Teacher, Subject
from accounts.models import User
from attendance.models import AttendanceRecord, AttendanceSession
from audit.models import AuditLog
from guardians.models import Guardian, StudentGuardian
from schools.models import School
from teacher_assignments.models import ClassSubjectTeacher


class AttendanceTests(TestCase):
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

        # Academic Year for School A (covers today)
        self.today = timezone.localdate()
        self.ay = AcademicYear.objects.create(
            school=self.school_a,
            name="2026-27",
            start_date=self.today.replace(month=1, day=1),
            end_date=self.today.replace(month=12, day=31),
            is_current=True,
        )

        # Teacher A
        self.teacher_user_a = User.objects.create_user(
            username="teacher_a",
            password="Password@123",
            role="teacher",
        )
        self.teacher_a = Teacher.objects.create(
            user=self.teacher_user_a,
            school=self.school_a,
            employee_id="T001",
        )

        # Class A with class_teacher = Teacher A
        self.class_a = SchoolClass.objects.create(
            name="10",
            section="A",
            school=self.school_a,
            class_teacher=self.teacher_a,
        )

        # Students in Class A
        self.student_user_1 = User.objects.create_user(username="s1", role="student", first_name="Aarav", last_name="Sharma")
        self.student_1 = Student.objects.create(
            user=self.student_user_1,
            school=self.school_a,
            class_section=self.class_a,
            admission_number="SCH-A-001",
        )
        self.student_user_2 = User.objects.create_user(username="s2", role="student", first_name="Bhavna", last_name="Patel")
        self.student_2 = Student.objects.create(
            user=self.student_user_2,
            school=self.school_a,
            class_section=self.class_a,
            admission_number="SCH-A-002",
        )

        # Another teacher in School A
        self.teacher_user_b = User.objects.create_user(
            username="teacher_b",
            password="Password@123",
            role="teacher",
        )
        self.teacher_b = Teacher.objects.create(
            user=self.teacher_user_b,
            school=self.school_a,
            employee_id="T002",
        )

    def test_class_attendance_defaults_to_present(self):
        self.client.force_authenticate(user=self.teacher_user_a)
        res = self.client.get(f"/api/v1/attendance/class/{self.class_a.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["exists"])
        self.assertEqual(len(res.data["students"]), 2)
        for s in res.data["students"]:
            self.assertEqual(s["status"], "present")

    def test_teacher_can_take_attendance_for_own_class_today(self):
        self.client.force_authenticate(user=self.teacher_user_a)
        payload = {
            "date": str(self.today),
            "records": [
                {"studentId": self.student_1.id, "status": "present", "remark": ""},
                {"studentId": self.student_2.id, "status": "absent", "remark": "Sick"},
            ],
        }
        res = self.client.put(f"/api/v1/attendance/class/{self.class_a.id}/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["exists"])

        # Check in DB
        self.assertEqual(AttendanceSession.objects.filter(school_class=self.class_a, date=self.today).count(), 1)
        self.assertEqual(AttendanceRecord.objects.filter(student=self.student_2, status="absent").count(), 1)

        # Audit log written
        self.assertTrue(AuditLog.objects.filter(school=self.school_a, action="attendance.create").exists())

    def test_teacher_cannot_take_attendance_for_other_class(self):
        self.client.force_authenticate(user=self.teacher_user_b)
        payload = {
            "date": str(self.today),
            "records": [
                {"studentId": self.student_1.id, "status": "present"},
                {"studentId": self.student_2.id, "status": "present"},
            ],
        }
        res = self.client.put(f"/api/v1/attendance/class/{self.class_a.id}/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_foreign_or_missing_students_rejected(self):
        self.client.force_authenticate(user=self.teacher_user_a)

        # Missing student 2
        payload_missing = {
            "date": str(self.today),
            "records": [
                {"studentId": self.student_1.id, "status": "present"},
            ],
        }
        res = self.client.put(f"/api/v1/attendance/class/{self.class_a.id}/", data=payload_missing, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("records", res.data)

    def test_principal_can_edit_with_audit_before_after(self):
        # Teacher marks initially
        self.client.force_authenticate(user=self.teacher_user_a)
        self.client.put(
            f"/api/v1/attendance/class/{self.class_a.id}/",
            data={
                "date": str(self.today),
                "records": [
                    {"studentId": self.student_1.id, "status": "present"},
                    {"studentId": self.student_2.id, "status": "present"},
                ],
            },
            format="json",
        )

        # Principal edits student 2 to absent
        self.client.force_authenticate(user=self.principal_a)
        res_edit = self.client.put(
            f"/api/v1/attendance/class/{self.class_a.id}/",
            data={
                "date": str(self.today),
                "records": [
                    {"studentId": self.student_1.id, "status": "present"},
                    {"studentId": self.student_2.id, "status": "absent", "remark": "Principal verified absent"},
                ],
            },
            format="json",
        )
        self.assertEqual(res_edit.status_code, status.HTTP_200_OK)

        # Check AuditLog for update
        update_log = AuditLog.objects.filter(school=self.school_a, action="attendance.update").first()
        self.assertIsNotNone(update_log)
        self.assertEqual(update_log.changes["before"][str(self.student_2.id)], "present")
        self.assertEqual(update_log.changes["after"][str(self.student_2.id)], "absent")

    def test_summary_and_trend(self):
        # Mark 1 present, 1 absent
        self.client.force_authenticate(user=self.teacher_user_a)
        self.client.put(
            f"/api/v1/attendance/class/{self.class_a.id}/",
            data={
                "date": str(self.today),
                "records": [
                    {"studentId": self.student_1.id, "status": "present"},
                    {"studentId": self.student_2.id, "status": "absent"},
                ],
            },
            format="json",
        )

        self.client.force_authenticate(user=self.principal_a)
        res_sum = self.client.get("/api/v1/attendance/summary/")
        self.assertEqual(res_sum.status_code, status.HTTP_200_OK)
        self.assertEqual(res_sum.data["totalStudents"], 2)
        self.assertEqual(res_sum.data["present"], 1)
        self.assertEqual(res_sum.data["absent"], 1)
        self.assertEqual(res_sum.data["presentPercent"], 50.0)

        res_trend = self.client.get("/api/v1/attendance/trend/?days=7")
        self.assertEqual(res_trend.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_trend.data), 7)
        self.assertEqual(res_trend.data[-1]["presentPercent"], 50.0)

    def test_subject_teacher_cannot_post_attendance(self):
        # Teacher B is assigned as subject teacher (e.g. Mathematics) for Class A, but is NOT class teacher
        subj = Subject.objects.create(name="Mathematics", code="MATH-10", school=self.school_a)
        ClassSubjectTeacher.objects.create(
            school=self.school_a,
            school_class=self.class_a,
            subject=subj,
            teacher=self.teacher_b,
        )

        self.client.force_authenticate(user=self.teacher_user_b)
        payload = {
            "date": str(self.today),
            "records": [
                {"studentId": self.student_1.id, "status": "present"},
                {"studentId": self.student_2.id, "status": "present"},
            ],
        }
        res_put = self.client.put(f"/api/v1/attendance/class/{self.class_a.id}/", data=payload, format="json")
        self.assertEqual(res_put.status_code, status.HTTP_403_FORBIDDEN)

        res_post = self.client.post(f"/api/v1/attendance/class/{self.class_a.id}/", data=payload, format="json")
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_past_date_rejected(self):
        self.client.force_authenticate(user=self.teacher_user_a)
        past_date = self.today - timezone.timedelta(days=2)
        payload = {
            "date": str(past_date),
            "records": [
                {"studentId": self.student_1.id, "status": "present"},
                {"studentId": self.student_2.id, "status": "present"},
            ],
        }
        res = self.client.post(f"/api/v1/attendance/class/{self.class_a.id}/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("detail", res.data)

    def test_principal_past_date_allowed_and_logged(self):
        self.client.force_authenticate(user=self.principal_a)
        past_date = self.today - timezone.timedelta(days=2)
        payload = {
            "date": str(past_date),
            "records": [
                {"studentId": self.student_1.id, "status": "present"},
                {"studentId": self.student_2.id, "status": "absent", "remark": "Past date medical"},
            ],
        }
        res = self.client.post(f"/api/v1/attendance/class/{self.class_a.id}/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # AuditLog row exists for attendance.create
        audit_entry = AuditLog.objects.filter(school=self.school_a, action="attendance.create").filter(changes__date=str(past_date)).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.actor, self.principal_a)

    def test_user_from_another_school_forbidden(self):
        # Create School B and its principal and teacher
        school_b = School.objects.create(name="School B", code="SCH-B", address="Road B", city="Indore")
        principal_b = User.objects.create_user(username="principal_b", password="Password@123", role="principal")
        school_b.principal = principal_b
        school_b.save()

        teacher_user_b2 = User.objects.create_user(username="teacher_b2", password="Password@123", role="teacher")
        Teacher.objects.create(user=teacher_user_b2, school=school_b, employee_id="TB02")

        payload = {
            "date": str(self.today),
            "records": [
                {"studentId": self.student_1.id, "status": "present"},
                {"studentId": self.student_2.id, "status": "present"},
            ],
        }

        # Principal B gets 403 on School A's class
        self.client.force_authenticate(user=principal_b)
        res_p = self.client.get(f"/api/v1/attendance/class/{self.class_a.id}/")
        self.assertEqual(res_p.status_code, status.HTTP_403_FORBIDDEN)
        res_p_post = self.client.post(f"/api/v1/attendance/class/{self.class_a.id}/", data=payload, format="json")
        self.assertEqual(res_p_post.status_code, status.HTTP_403_FORBIDDEN)

        # Teacher B from School B gets 403
        self.client.force_authenticate(user=teacher_user_b2)
        res_t = self.client.get(f"/api/v1/attendance/class/{self.class_a.id}/")
        self.assertEqual(res_t.status_code, status.HTTP_403_FORBIDDEN)
        res_t_post = self.client.post(f"/api/v1/attendance/class/{self.class_a.id}/", data=payload, format="json")
        self.assertEqual(res_t_post.status_code, status.HTTP_403_FORBIDDEN)

    def test_display_admission_number_in_roster(self):
        self.client.force_authenticate(user=self.teacher_user_a)
        res = self.client.get(f"/api/v1/attendance/class/{self.class_a.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # s1 has admission_number="SCH-A-001", so displayAdmissionNumber should be "001"
        s1_data = next((s for s in res.data["students"] if s["studentId"] == self.student_1.id), None)
        self.assertIsNotNone(s1_data)
        self.assertEqual(s1_data["admissionNumber"], "SCH-A-001")
        self.assertEqual(s1_data["displayAdmissionNumber"], "001")
