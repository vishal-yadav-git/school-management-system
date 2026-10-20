from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "school",
        "actor",
        "action",
        "object_type",
        "object_id",
        "ip_address",
    )
    list_filter = ("school", "action", "created_at")
    search_fields = ("action", "object_type", "actor__username", "school__name")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
