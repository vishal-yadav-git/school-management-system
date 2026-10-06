from django.urls import path

from . import views
from . import views_admin

urlpatterns = [
    # Auth
    path("auth/csrf/", views.csrf, name="api_csrf"),
    path("auth/login/", views.login_view, name="api_login"),
    path("auth/register/", views.register_view, name="api_register"),
    path("auth/logout/", views.logout_view, name="api_logout"),
    path("auth/me/", views.me, name="api_me"),

    # Public Directory & Dashboard
    path("schools/", views.schools, name="api_schools"),
    path("schools/<int:pk>/", views.school_detail, name="api_school_detail"),
    path("dashboard/stats/", views.dashboard_stats, name="api_dashboard_stats"),

    # Existing Academic endpoints (retained for backward compatibility)
    path("academics/classes/", views.classes, name="api_classes"),
    path("academics/teachers/", views.teachers, name="api_teachers"),
    path("academics/students/", views.students, name="api_students"),
    path("teacher/my-students/", views.my_students, name="api_my_students"),
    path("student/me/", views.student_me, name="api_student_me"),

    # Institute Admin / CRUD Endpoints (Scoped by School)
    path("admin/classes/", views_admin.admin_classes, name="api_admin_classes"),
    path("admin/classes/<int:pk>/", views_admin.admin_class_detail, name="api_admin_class_detail"),

    path("admin/teachers/", views_admin.admin_teachers, name="api_admin_teachers"),
    path("admin/teachers/<int:pk>/", views_admin.admin_teacher_detail, name="api_admin_teacher_detail"),

    path("admin/students/", views_admin.admin_students, name="api_admin_students"),
    path("admin/students/<int:pk>/", views_admin.admin_student_detail, name="api_admin_student_detail"),

    # Superuser Only Management
    path("admin/schools/", views_admin.admin_schools_manage, name="api_admin_schools_manage"),
    path("admin/schools/<int:pk>/", views_admin.admin_school_detail_manage, name="api_admin_school_detail_manage"),

    path("admin/principals/", views_admin.admin_principals_manage, name="api_admin_principals_manage"),
    path("admin/principals/<int:pk>/", views_admin.admin_principal_detail_manage, name="api_admin_principal_detail_manage"),

    # Excel / CSV Import Flow
    path("admin/import/preview/", views_admin.admin_import_preview, name="api_admin_import_preview"),
    path("admin/import/confirm/", views_admin.admin_import_confirm, name="api_admin_import_confirm"),
]
