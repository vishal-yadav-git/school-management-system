from django.conf import settings
from django.db import models


class TeacherPermission(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="teacher_permissions",
    )
    teacher = models.ForeignKey(
        "academics.Teacher",
        on_delete=models.CASCADE,
        related_name="permissions",
    )
    permission_key = models.CharField(max_length=50)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_teacher_permissions",
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "teacher", "permission_key"],
                name="unique_teacher_permission",
            ),
        ]
        ordering = ["-granted_at"]

    def __str__(self):
        return f"{self.teacher.user.get_full_name()} - {self.permission_key} ({self.school.name})"


class ClassSubjectTeacher(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="class_subject_teachers",
    )
    school_class = models.ForeignKey(
        "academics.SchoolClass",
        on_delete=models.CASCADE,
        related_name="subject_teachers",
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="class_teachers",
    )
    teacher = models.ForeignKey(
        "academics.Teacher",
        on_delete=models.CASCADE,
        related_name="subject_assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "subject"],
                name="unique_class_subject_teacher",
            ),
        ]
        ordering = ["school_class", "subject"]

    def __str__(self):
        return f"{self.school_class.name}-{self.school_class.section} | {self.subject.name} -> {self.teacher.user.get_full_name()}"
