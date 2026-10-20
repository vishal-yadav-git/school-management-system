from django.contrib import admin
from .models import ClassSubjectTeacher, TeacherPermission


@admin.register(TeacherPermission)
class TeacherPermissionAdmin(admin.ModelAdmin):
    list_display = ("teacher", "permission_key", "school", "granted_by", "granted_at")
    list_filter = ("school", "permission_key")
    search_fields = ("teacher__user__first_name", "teacher__user__last_name", "teacher__employee_id")


@admin.register(ClassSubjectTeacher)
class ClassSubjectTeacherAdmin(admin.ModelAdmin):
    list_display = ("school_class", "subject", "teacher", "school", "assigned_at")
    list_filter = ("school", "school_class")
    search_fields = ("school_class__name", "subject__name", "teacher__user__first_name", "teacher__user__last_name")
