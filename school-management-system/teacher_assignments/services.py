from django.core.exceptions import ValidationError

from audit.services import log_action
from .models import ClassSubjectTeacher, TeacherPermission

VALID_PERMISSION_KEYS = [
    "attendance_backdate",
    "manage_syllabus",
    "publish_notices",
    "view_student_contacts",
]


def validate_permission_key(key):
    if key not in VALID_PERMISSION_KEYS:
        raise ValidationError(
            f"Invalid permission key '{key}'. Must be one of: {', '.join(VALID_PERMISSION_KEYS)}"
        )


def grant_permission(school, teacher, permission_key, actor, request=None):
    """
    Grants a granular permission to a teacher within a school.
    Logs permission.grant in AuditLog.
    """
    validate_permission_key(permission_key)

    if teacher.school_id != school.id:
        raise ValidationError("Teacher does not belong to this school.")

    perm, created = TeacherPermission.objects.get_or_create(
        school=school,
        teacher=teacher,
        permission_key=permission_key,
        defaults={"granted_by": actor},
    )

    if created:
        log_action(
            actor=actor,
            school=school,
            action="permission.grant",
            obj=teacher,
            changes={"permission_key": permission_key},
            request=request,
        )

    return perm


def revoke_permission(school, teacher, permission_key, actor, request=None):
    """
    Revokes a granular permission from a teacher within a school.
    Logs permission.revoke in AuditLog.
    """
    validate_permission_key(permission_key)

    deleted_count, _ = TeacherPermission.objects.filter(
        school=school,
        teacher=teacher,
        permission_key=permission_key,
    ).delete()

    if deleted_count > 0:
        log_action(
            actor=actor,
            school=school,
            action="permission.revoke",
            obj=teacher,
            changes={"permission_key": permission_key},
            request=request,
        )

    return True


def has_teacher_permission(teacher, permission_key):
    """
    Checks if a teacher has a specific granted permission key.
    """
    if not teacher:
        return False
    return TeacherPermission.objects.filter(
        teacher=teacher,
        permission_key=permission_key,
    ).exists()


def assign_class_subject_teacher(school, school_class, subject, teacher, actor=None, request=None):
    """
    Assigns a teacher to teach a subject for a specific class section.
    Enforces that only one teacher is assigned per subject per class.
    """
    if school_class.school_id != school.id:
        raise ValidationError("Class does not belong to this school.")
    if subject.school_id != school.id:
        raise ValidationError("Subject does not belong to this school.")
    if teacher.school_id != school.id:
        raise ValidationError("Teacher does not belong to this school.")

    cst, created = ClassSubjectTeacher.objects.update_or_create(
        school_class=school_class,
        subject=subject,
        defaults={
            "school": school,
            "teacher": teacher,
        },
    )

    return cst
