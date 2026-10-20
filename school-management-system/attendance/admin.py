from django.contrib import admin
from .models import AttendanceRecord, AttendanceSession


class AttendanceRecordInline(admin.TabularInline):
    model = AttendanceRecord
    extra = 0


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ("school_class", "date", "school", "academic_year", "taken_by")
    list_filter = ("school", "academic_year", "date")
    search_fields = ("school_class__name", "school_class__section", "taken_by__username")
    inlines = [AttendanceRecordInline]


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("student", "session", "status", "remark")
    list_filter = ("status", "session__date")
    search_fields = ("student__admission_number", "student__user__username", "remark")
