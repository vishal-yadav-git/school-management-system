from django.contrib import admin
from .models import UserSecurity


@admin.register(UserSecurity)
class UserSecurityAdmin(admin.ModelAdmin):
    list_display = ("user", "must_change_password", "password_changed_at", "updated_at")
    list_filter = ("must_change_password",)
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
