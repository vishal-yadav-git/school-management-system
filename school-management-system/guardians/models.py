from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Guardian(models.Model):
    STATUS_CHOICES = [
        ("unlinked", "Unlinked"),
        ("pending", "Pending"),
        ("approved", "Approved"),
    ]

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="guardians",
    )
    full_name = models.CharField(max_length=150)
    mobile = models.CharField(max_length=15)
    email = models.EmailField(blank=True, default="")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guardians",
    )
    requested_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_guardians",
    )
    link_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="unlinked",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decided_guardians",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "mobile"],
                name="unique_guardian_school_mobile",
            ),
            models.UniqueConstraint(
                fields=["school", "user"],
                condition=models.Q(user__isnull=False),
                name="unique_guardian_school_user",
            ),
        ]
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.mobile}) - {self.school.name}"


class StudentGuardian(models.Model):
    RELATION_CHOICES = [
        ("father", "Father"),
        ("mother", "Mother"),
        ("guardian", "Guardian"),
        ("other", "Other"),
    ]

    student = models.ForeignKey(
        "academics.Student",
        on_delete=models.CASCADE,
        related_name="student_guardians",
    )
    guardian = models.ForeignKey(
        Guardian,
        on_delete=models.CASCADE,
        related_name="guardian_students",
    )
    relation = models.CharField(
        max_length=20,
        choices=RELATION_CHOICES,
        default="guardian",
    )
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "guardian"],
                name="unique_student_guardian",
            ),
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(is_primary=True),
                name="unique_primary_guardian_per_student",
            ),
        ]

    def clean(self):
        super().clean()
        if self.student and self.guardian and self.student.school_id != self.guardian.school_id:
            raise ValidationError("Guardian must belong to the same school as the student.")

    def __str__(self):
        return f"{self.student.user.get_full_name()} -> {self.guardian.full_name} ({self.relation})"
