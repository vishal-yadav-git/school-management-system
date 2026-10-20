from django.conf import settings
from django.db import models


class AttendanceSession(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="attendance_sessions",
    )
    school_class = models.ForeignKey(
        "academics.SchoolClass",
        on_delete=models.CASCADE,
        related_name="attendance_sessions",
    )
    academic_year = models.ForeignKey(
        "academic_year.AcademicYear",
        on_delete=models.CASCADE,
        related_name="attendance_sessions",
    )
    date = models.DateField()
    taken_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="taken_attendance_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "date"],
                name="unique_class_date_session",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "date"]),
        ]
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.school_class} on {self.date}"


class AttendanceRecord(models.Model):
    STATUS_CHOICES = [
        ("present", "Present"),
        ("absent", "Absent"),
        ("late", "Late"),
        ("leave", "Leave"),
    ]

    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.CASCADE,
        related_name="records",
    )
    student = models.ForeignKey(
        "academics.Student",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="present",
    )
    remark = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "student"],
                name="unique_session_student",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "session"]),
        ]

    def __str__(self):
        return f"{self.student} - {self.status}"
