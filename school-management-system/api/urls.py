from django.urls import path

from . import views
from . import views_admin
from academic_year import views as views_ay
from audit import views as views_audit
from guardians import views as views_guardians
from attendance import views as views_attendance
from notices import views as views_notices
from organizations import views as views_org
from credentials import views as views_credentials
from importers import views as views_importers
from teacher_assignments import views as views_ta
from syllabus import views as views_syll

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

    # Wave 1: Academic Year & Audit
    path("academic-years/", views_ay.academic_years, name="api_academic_years"),
    path("audit/", views_audit.audit_logs, name="api_audit_logs"),

    # Wave 1: Guardians
    path("students/<int:pk>/guardians/", views_guardians.student_guardians, name="api_student_guardians"),
    path("students/<int:pk>/guardians/<int:guardian_id>/", views_guardians.student_guardian_delete, name="api_student_guardian_delete"),
    path("guardians/claim/", views_guardians.guardian_claim, name="api_guardian_claim"),
    path("guardians/link-requests/", views_guardians.guardian_link_requests, name="api_guardian_link_requests"),
    path("guardians/link-requests/<int:guardian_id>/approve/", views_guardians.guardian_approve, name="api_guardian_approve"),
    path("guardians/link-requests/<int:guardian_id>/reject/", views_guardians.guardian_reject, name="api_guardian_reject"),
    path("parent/children/", views_guardians.parent_children, name="api_parent_children"),

    # Wave 1: Attendance
    path("attendance/class/<int:class_id>/", views_attendance.class_attendance, name="api_class_attendance"),
    path("attendance/summary/", views_attendance.attendance_summary, name="api_attendance_summary"),
    path("attendance/trend/", views_attendance.attendance_trend, name="api_attendance_trend"),
    path("attendance/student/<int:student_id>/", views_attendance.student_attendance, name="api_student_attendance"),

    # Wave 1: Notices
    path("notices/", views_notices.notices_list, name="api_notices_list"),
    path("notices/<int:pk>/", views_notices.notice_detail, name="api_notice_detail"),

    # Wave 2: Organizations & Multi-Campus
    path("auth/register-org/", views_org.register_org, name="api_register_org"),
    path("auth/verify-email/", views_org.verify_email, name="api_verify_email"),
    path("organizations/campuses/", views_org.campuses_list, name="api_campuses_list"),
    path("organizations/switch-campus/", views_org.switch_campus, name="api_switch_campus"),

    # Wave 2: Setup Wizard & Principal Classes
    path("setup/status/", views_org.setup_status, name="api_setup_status"),
    path("classes/", views_org.principal_classes, name="api_classes_principal"),

    # Wave 2: Step 3 - Credentials & Security
    path("credentials/reset-password/", views_credentials.principal_reset_password, name="api_principal_reset_password"),
    path("auth/change-password/", views_credentials.change_password, name="api_change_password"),

    # Wave 2: Step 4 - Importers (Templates, Preview, Confirm)
    path("import/template/teachers/", views_importers.teacher_template_download, name="api_import_teacher_template"),
    path("import/template/students/", views_importers.student_template_download, name="api_import_student_template"),
    path("import/preview/", views_importers.import_preview, name="api_import_preview"),
    path("import/confirm/", views_importers.import_confirm, name="api_import_confirm"),

    # Wave 2: Step 5 - Teacher Permissions & Assignments
    path("teachers/<int:teacher_id>/permissions/", views_ta.teacher_permissions_view, name="api_teacher_permissions"),
    path("classes/<int:class_id>/subject-teachers/", views_ta.class_subject_teachers_view, name="api_class_subject_teachers"),

    # Wave 2: Step 6 - Syllabus Management
    path("subjects/<int:subject_id>/syllabus/", views_syll.subject_syllabus_view, name="api_subject_syllabus"),
    path("subjects/<int:subject_id>/units/", views_syll.create_unit_view, name="api_create_unit"),
    path("units/<int:unit_id>/topics/", views_syll.create_topic_view, name="api_create_topic"),
    path("topics/<int:topic_id>/status/", views_syll.update_topic_status_view, name="api_update_topic_status"),
]




