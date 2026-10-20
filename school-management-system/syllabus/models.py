from django.db import models


class Unit(models.Model):
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="units",
    )
    unit_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "unit_number"],
                name="unique_subject_unit_number",
            ),
        ]
        ordering = ["unit_number"]

    def __str__(self):
        return f"{self.subject.name} - Unit {self.unit_number}: {self.title}"


class Topic(models.Model):
    STATUS_CHOICES = [
        ("not_started", "Not Started"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
    ]

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="topics",
    )
    topic_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="not_started",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["unit", "topic_number"],
                name="unique_unit_topic_number",
            ),
        ]
        ordering = ["topic_number"]

    def __str__(self):
        return f"Unit {self.unit.unit_number}.{self.topic_number} - {self.title} [{self.status}]"
