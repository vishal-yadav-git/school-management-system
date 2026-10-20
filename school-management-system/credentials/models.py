from django.conf import settings
from django.db import models


class UserSecurity(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="security",
    )
    must_change_password = models.BooleanField(default=False)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Security"
        verbose_name_plural = "User Securities"

    def __str__(self):
        return f"{self.user.username} (must_change={self.must_change_password})"
