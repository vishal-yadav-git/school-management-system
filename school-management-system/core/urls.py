from django.urls import path

from .views import (
    home,
    dashboard,
    admin_dashboard,
    principal_dashboard,
    teacher_dashboard,
    student_dashboard,
    parent_dashboard,
)


urlpatterns = [

    path(
        '',
        home,
        name='home'
    ),

    path(
        'dashboard/',
        dashboard,
        name='dashboard'
    ),

    path(
        'admin-dashboard/',
        admin_dashboard,
        name='admin_dashboard'
    ),

    path(
        'principal-dashboard/',
        principal_dashboard,
        name='principal_dashboard'
    ),

    path(
        'teacher-dashboard/',
        teacher_dashboard,
        name='teacher_dashboard'
    ),

    path(
        'student-dashboard/',
        student_dashboard,
        name='student_dashboard'
    ),

    path(
        'parent-dashboard/',
        parent_dashboard,
        name='parent_dashboard'
    ),
]