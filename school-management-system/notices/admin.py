from django.contrib import admin
from .models import Notice


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ("title", "school", "audience", "is_pinned", "expires_on", "created_by", "created_at")
    list_filter = ("school", "audience", "is_pinned", "expires_on")
    search_fields = ("title", "body", "school__name")
