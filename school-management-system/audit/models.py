from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=50)
    object_type = models.CharField(max_length=50, blank=True, default="")
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["school", "-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at} - {self.action} by {self.actor or 'System'}"
