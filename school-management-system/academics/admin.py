from django.contrib import admin
from .models import Teacher, Student, SchoolClass, Subject


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):

    list_display = (
        'employee_id',
        'user',
        'school',
        'designation',
        'qualification',
        'joining_date',
    )

    search_fields = (
        'employee_id',
        'user__username',
        'user__first_name',
        'user__last_name',
    )

    list_filter = (
        'school',
        'designation',
    )


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):

    list_display = (
        'admission_number',
        'user',
        'school',
        'class_section',
        'gender',
    )

    search_fields = (
        'admission_number',
        'user__username',
        'user__first_name',
        'user__last_name',
    )

    list_filter = (
        'school',
        'gender',
    )


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):

    list_display = (
        'name',
        'section',
        'school',
        'class_teacher',
    )

    list_filter = (
        'school',
        'name',
    )


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):

    list_display = (
        'name',
        'code',
        'school',
    )

    search_fields = (
        'name',
        'code',
    )

    list_filter = (
        'school',
    )