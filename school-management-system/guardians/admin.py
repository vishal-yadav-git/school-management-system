from django.contrib import admin
from .models import Guardian, StudentGuardian


class StudentGuardianInline(admin.TabularInline):
    model = StudentGuardian
    extra = 1


@admin.register(Guardian)
class GuardianAdmin(admin.ModelAdmin):
    list_display = ("full_name", "mobile", "school", "link_status", "user", "requested_user")
    list_filter = ("school", "link_status")
    search_fields = ("full_name", "mobile", "user__username")
    inlines = [StudentGuardianInline]


@admin.register(StudentGuardian)
class StudentGuardianAdmin(admin.ModelAdmin):
    list_display = ("student", "guardian", "relation", "is_primary")
    list_filter = ("relation", "is_primary")
    search_fields = ("student__admission_number", "guardian__full_name", "guardian__mobile")
