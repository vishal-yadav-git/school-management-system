from django.urls import path

from . import views

urlpatterns = [
    path("auth/csrf/", views.csrf, name="api_csrf"),
    path("auth/login/", views.login_view, name="api_login"),
    path("auth/logout/", views.logout_view, name="api_logout"),
    path("auth/me/", views.me, name="api_me"),
    path("schools/", views.schools, name="api_schools"),
    path("schools/<int:pk>/", views.school_detail, name="api_school_detail"),
    path("dashboard/stats/", views.dashboard_stats, name="api_dashboard_stats"),
    path("academics/classes/", views.classes, name="api_classes"),
    path("academics/teachers/", views.teachers, name="api_teachers"),
    path("academics/students/", views.students, name="api_students"),
    path("teacher/my-students/", views.my_students, name="api_my_students"),
]
