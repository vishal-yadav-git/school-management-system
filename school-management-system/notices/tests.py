from datetime import timedelta
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from academics.models import SchoolClass, Student, Teacher
from accounts.models import User
from audit.models import AuditLog
from guardians.models import Guardian, StudentGuardian
from notices.models import Notice
from schools.models import School


class NoticeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.today = timezone.localdate()

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

        # Teacher A in School A
        self.teacher_user_a = User.objects.create_user(username="teacher_a", role="teacher")
        self.teacher_a = Teacher.objects.create(user=self.teacher_user_a, school=self.school_a, employee_id="T01")

        # Class 10-A with Teacher A as class teacher
        self.class_10a = SchoolClass.objects.create(name="10", section="A", school=self.school_a, class_teacher=self.teacher_a)

        # Class 10-B with no teacher
        self.class_10b = SchoolClass.objects.create(name="10", section="B", school=self.school_a)

        # Student in 10-A
        self.student_user_a = User.objects.create_user(username="student_a", role="student")
        self.student_a = Student.objects.create(
            user=self.student_user_a,
            school=self.school_a,
            class_section=self.class_10a,
            admission_number="SCH-A-101",
        )

        # Student in 10-B
        self.student_user_b = User.objects.create_user(username="student_b", role="student")
        self.student_b = Student.objects.create(
            user=self.student_user_b,
            school=self.school_a,
            class_section=self.class_10b,
            admission_number="SCH-A-102",
        )

        # Approved parent linked to student A
        self.parent_user = User.objects.create_user(username="parent_a", role="parent", mobile="9826011111")
        self.guardian = Guardian.objects.create(
            school=self.school_a,
            full_name="Parent A",
            mobile="9826011111",
            user=self.parent_user,
            link_status="approved",
        )
        StudentGuardian.objects.create(student=self.student_a, guardian=self.guardian, relation="father", is_primary=True)

    def test_principal_create_update_delete_notice(self):
        self.client.force_authenticate(user=self.principal_a)

        # Create notice
        res = self.client.post(
            "/api/v1/notices/",
            data={
                "title": "Annual Sports Day",
                "body": "Sports day will be held on Friday.",
                "audience": "all",
                "isPinned": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        notice_id = res.data["id"]
        self.assertTrue(res.data["isPinned"])

        # Verify audit log
        self.assertTrue(AuditLog.objects.filter(school=self.school_a, action="notice.create").exists())

        # Update notice
        res_patch = self.client.patch(
            f"/api/v1/notices/{notice_id}/",
            data={"title": "Annual Sports Day - Postponed"},
            format="json",
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data["title"], "Annual Sports Day - Postponed")

        # Delete notice
        res_del = self.client.delete(f"/api/v1/notices/{notice_id}/")
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
        self.assertFalse(Notice.objects.filter(id=notice_id).exists())

    def test_audience_visibility_matrix(self):
        # 1. Notice for Teachers only
        Notice.objects.create(
            school=self.school_a,
            title="Faculty Meeting",
            body="Meeting at 4pm",
            audience="teachers",
        )

        # 2. Notice for Parents only
        Notice.objects.create(
            school=self.school_a,
            title="PTM Next Week",
            body="Please attend",
            audience="parents",
        )

        # 3. Notice for Class 10-A only
        n_class = Notice.objects.create(
            school=self.school_a,
            title="10-A Science Project",
            body="Submit by Monday",
            audience="classes",
        )
        n_class.target_classes.add(self.class_10a)

        # Teacher checks notices: sees Faculty Meeting and 10-A Science Project (because class_teacher), but NOT PTM Next Week
        self.client.force_authenticate(user=self.teacher_user_a)
        res_teacher = self.client.get("/api/v1/notices/")
        teacher_titles = [n["title"] for n in res_teacher.data]
        self.assertIn("Faculty Meeting", teacher_titles)
        self.assertIn("10-A Science Project", teacher_titles)
        self.assertNotIn("PTM Next Week", teacher_titles)

        # Parent checks notices: sees PTM Next Week and 10-A Science Project (their child is in 10-A), but NOT Faculty Meeting
        self.client.force_authenticate(user=self.parent_user)
        res_parent = self.client.get("/api/v1/notices/")
        parent_titles = [n["title"] for n in res_parent.data]
        self.assertIn("PTM Next Week", parent_titles)
        self.assertIn("10-A Science Project", parent_titles)
        self.assertNotIn("Faculty Meeting", parent_titles)

        # Student in 10-A sees 10-A Science Project
        self.client.force_authenticate(user=self.student_user_a)
        res_s_a = self.client.get("/api/v1/notices/")
        s_a_titles = [n["title"] for n in res_s_a.data]
        self.assertIn("10-A Science Project", s_a_titles)

        # Student in 10-B does NOT see 10-A Science Project
        self.client.force_authenticate(user=self.student_user_b)
        res_s_b = self.client.get("/api/v1/notices/")
        s_b_titles = [n["title"] for n in res_s_b.data]
        self.assertNotIn("10-A Science Project", s_b_titles)

    def test_expired_notices_hidden_from_non_principals(self):
        # Notice expired yesterday
        Notice.objects.create(
            school=self.school_a,
            title="Yesterday Holiday",
            body="Holiday",
            audience="all",
            expires_on=self.today - timedelta(days=1),
        )

        # Student sees nothing
        self.client.force_authenticate(user=self.student_user_a)
        res_s = self.client.get("/api/v1/notices/")
        self.assertEqual(len(res_s.data), 0)

        # Principal still sees expired notices
        self.client.force_authenticate(user=self.principal_a)
        res_p = self.client.get("/api/v1/notices/")
        self.assertEqual(len(res_p.data), 1)
        self.assertEqual(res_p.data[0]["title"], "Yesterday Holiday")
