from django.conf import settings
from django.db import models


class Notice(models.Model):
    AUDIENCE_CHOICES = [
        ("all", "All"),
        ("parents", "Parents"),
        ("teachers", "Teachers"),
        ("classes", "Classes"),
    ]

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="notices",
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    audience = models.CharField(
        max_length=20,
        choices=AUDIENCE_CHOICES,
        default="all",
    )
    target_classes = models.ManyToManyField(
        "academics.SchoolClass",
        blank=True,
        related_name="notices",
    )
    is_pinned = models.BooleanField(default=False)
    expires_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_notices",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["school", "-created_at"]),
        ]
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.school.name})"
