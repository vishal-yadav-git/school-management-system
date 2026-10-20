from rest_framework import status
from rest_framework.test import APITestCase

from academics.models import SchoolClass, Student, Subject, Teacher
from accounts.models import User
from guardians.models import Guardian, StudentGuardian
from schools.models import School
from syllabus.models import Topic, Unit
from teacher_assignments.models import ClassSubjectTeacher, TeacherPermission


class SyllabusTests(APITestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="School A", code="SCHA")
        self.school_b = School.objects.create(name="School B", code="SCHB")

        # Principal
        self.principal_a = User.objects.create_user(
            username="principal_a",
            email="principal_a@example.com",
            password="StrongPassword@123!",
            role="principal",
        )
        self.school_a.principal = self.principal_a
        self.school_a.save()

        # Subject
        self.subject = Subject.objects.create(
            school=self.school_a,
            name="Physics",
            code="PHY10",
        )

        self.class_10a = SchoolClass.objects.create(
            school=self.school_a,
            name="10",
            section="A",
        )

        # Assigned Teacher
        self.teacher_user_assigned = User.objects.create_user(
            username="teacher_assigned",
            email="ta@example.com",
            password="Password@123!",
            role="teacher",
        )
        self.teacher_assigned = Teacher.objects.create(
            user=self.teacher_user_assigned,
            school=self.school_a,
            employee_id="EMP-TA",
        )
        ClassSubjectTeacher.objects.create(
            school=self.school_a,
            school_class=self.class_10a,
            subject=self.subject,
            teacher=self.teacher_assigned,
        )

        # Permitted Teacher (via manage_syllabus)
        self.teacher_user_permitted = User.objects.create_user(
            username="teacher_permitted",
            email="tp@example.com",
            password="Password@123!",
            role="teacher",
        )
        self.teacher_permitted = Teacher.objects.create(
            user=self.teacher_user_permitted,
            school=self.school_a,
            employee_id="EMP-TP",
        )
        TeacherPermission.objects.create(
            school=self.school_a,
            teacher=self.teacher_permitted,
            permission_key="manage_syllabus",
            granted_by=self.principal_a,
        )

        # Unpermitted & Unassigned Teacher
        self.teacher_user_other = User.objects.create_user(
            username="teacher_other",
            email="to@example.com",
            password="Password@123!",
            role="teacher",
        )
        self.teacher_other = Teacher.objects.create(
            user=self.teacher_user_other,
            school=self.school_a,
            employee_id="EMP-TO",
        )

        # Student in School A
        self.student_user = User.objects.create_user(
            username="student_a",
            password="Password@123!",
            role="student",
        )
        self.student = Student.objects.create(
            user=self.student_user,
            school=self.school_a,
            class_section=self.class_10a,
            admission_number="ADM-A1",
        )

        # Parent of Student A
        self.parent_user = User.objects.create_user(
            username="9826011111",
            password="Password@123!",
            role="parent",
        )
        self.guardian = Guardian.objects.create(
            school=self.school_a,
            full_name="Parent A",
            mobile="9826011111",
            user=self.parent_user,
            link_status="approved",
        )
        StudentGuardian.objects.create(
            student=self.student,
            guardian=self.guardian,
            is_primary=True,
        )

        # Student in School B (for isolation)
        self.student_user_b = User.objects.create_user(
            username="student_b",
            password="Password@123!",
            role="student",
        )
        self.student_b = Student.objects.create(
            user=self.student_user_b,
            school=self.school_b,
            admission_number="ADM-B1",
        )

    def test_principal_can_create_unit_and_topic_and_duplicate_rejected(self):
        self.client.force_login(self.principal_a)

        # 1. Create Unit
        res_unit = self.client.post(
            f"/api/v1/subjects/{self.subject.id}/units/",
            {"unitNumber": 1, "title": "Thermodynamics", "description": "Heat and energy"},
        )
        self.assertEqual(res_unit.status_code, status.HTTP_201_CREATED)
        unit_id = res_unit.data["id"]

        # Duplicate unitNumber rejected
        res_dup_unit = self.client.post(
            f"/api/v1/subjects/{self.subject.id}/units/",
            {"unitNumber": 1, "title": "Another Title"},
        )
        self.assertEqual(res_dup_unit.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Create Topic
        res_topic = self.client.post(
            f"/api/v1/units/{unit_id}/topics/",
            {"topicNumber": 1, "title": "First Law of Thermodynamics", "description": "Conservation of energy"},
        )
        self.assertEqual(res_topic.status_code, status.HTTP_201_CREATED)
        topic_id = res_topic.data["id"]

        # Duplicate topicNumber rejected
        res_dup_topic = self.client.post(
            f"/api/v1/units/{unit_id}/topics/",
            {"topicNumber": 1, "title": "Another Topic"},
        )
        self.assertEqual(res_dup_topic.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assigned_and_permitted_teachers_can_edit_and_update_status(self):
        unit = Unit.objects.create(subject=self.subject, unit_number=1, title="Optics")
        topic = Topic.objects.create(unit=unit, topic_number=1, title="Reflection")

        # Assigned teacher can update status
        self.client.force_login(self.teacher_user_assigned)
        res_assigned = self.client.patch(
            f"/api/v1/topics/{topic.id}/status/",
            {"status": "in_progress"},
        )
        self.assertEqual(res_assigned.status_code, status.HTTP_200_OK)
        topic.refresh_from_db()
        self.assertEqual(topic.status, "in_progress")

        # Permitted teacher (via manage_syllabus) can complete topic
        self.client.force_login(self.teacher_user_permitted)
        res_permitted = self.client.patch(
            f"/api/v1/topics/{topic.id}/status/",
            {"status": "completed"},
        )
        self.assertEqual(res_permitted.status_code, status.HTTP_200_OK)
        topic.refresh_from_db()
        self.assertEqual(topic.status, "completed")
        self.assertIsNotNone(topic.completed_at)

        # Unpermitted teacher is rejected
        self.client.force_login(self.teacher_user_other)
        res_rejected = self.client.patch(
            f"/api/v1/topics/{topic.id}/status/",
            {"status": "not_started"},
        )
        self.assertEqual(res_rejected.status_code, status.HTTP_403_FORBIDDEN)

    def test_students_and_parents_read_only_and_cannot_modify(self):
        unit = Unit.objects.create(subject=self.subject, unit_number=1, title="Waves")
        topic = Topic.objects.create(unit=unit, topic_number=1, title="Doppler Effect")

        # Student can view
        self.client.force_login(self.student_user)
        res_s_view = self.client.get(f"/api/v1/subjects/{self.subject.id}/syllabus/")
        self.assertEqual(res_s_view.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_s_view.data), 1)

        # Student cannot modify topic
        res_s_edit = self.client.patch(
            f"/api/v1/topics/{topic.id}/status/",
            {"status": "completed"},
        )
        self.assertEqual(res_s_edit.status_code, status.HTTP_403_FORBIDDEN)

        # Parent can view
        self.client.force_login(self.parent_user)
        res_p_view = self.client.get(f"/api/v1/subjects/{self.subject.id}/syllabus/")
        self.assertEqual(res_p_view.status_code, status.HTTP_200_OK)

        # Parent cannot create unit
        res_p_create = self.client.post(
            f"/api/v1/subjects/{self.subject.id}/units/",
            {"unitNumber": 2, "title": "Unauthorized Unit"},
        )
        self.assertEqual(res_p_create.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_school_isolation(self):
        # Student B from school B cannot view school A's syllabus
        self.client.force_login(self.student_user_b)
        res = self.client.get(f"/api/v1/subjects/{self.subject.id}/syllabus/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
