from django.utils import timezone
from teacher_assignments.models import ClassSubjectTeacher
from teacher_assignments.services import has_teacher_permission


def can_user_view_syllabus(user, subject):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    school = subject.school
    role = getattr(user, "role", "")

    if role in ("principal", "admin"):
        return True

    if role == "teacher" and hasattr(user, "teacher_profile"):
        return user.teacher_profile.school_id == school.id

    if role == "student" and hasattr(user, "student_profile"):
        return user.student_profile.school_id == school.id

    if role == "parent":
        # Check if parent has any child in this school
        return user.guardians.filter(school=school).exists()

    return False


def can_user_edit_syllabus(user, subject):
    """
    Checks if a user can create/edit units and topics for a subject.
    Allowed for:
    - Superusers
    - School principal/admin
    - Teachers assigned to teach that subject
    - Teachers with the 'manage_syllabus' permission
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    school = subject.school
    role = getattr(user, "role", "")

    if role in ("principal", "admin"):
        return True

    if role == "teacher" and hasattr(user, "teacher_profile"):
        teacher = user.teacher_profile
        if teacher.school_id != school.id:
            return False

        if has_teacher_permission(teacher, "manage_syllabus"):
            return True

        if ClassSubjectTeacher.objects.filter(subject=subject, teacher=teacher).exists():
            return True

    return False


def can_user_update_topic_status(user, topic):
    """
    Allowed for principal, superuser, assigned subject teacher, or teacher with manage_syllabus.
    """
    return can_user_edit_syllabus(user, topic.unit.subject)
