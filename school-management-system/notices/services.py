from django.db.models import Q
from django.utils import timezone
from academics.models import SchoolClass, Student
from guardians.models import Guardian
from .models import Notice


def get_visible_notices_for_user(user, school_id=None):
    """
    Returns the queryset of notices visible to the requesting user based on role,
    school, audience, class associations, and expiration.
    """
    today = timezone.localdate()

    if user.is_superuser:
        if school_id:
            return Notice.objects.filter(school_id=school_id).distinct()
        return Notice.objects.all().distinct()

    role = getattr(user, "role", "")

    if role in ("principal", "admin"):
        school = getattr(user, "principal_school", None)
        if not school:
            return Notice.objects.none()
        return Notice.objects.filter(school=school).distinct()

    # For non-admin/non-principal, hide expired notices
    active_filter = Q(expires_on__isnull=True) | Q(expires_on__gte=today)

    if role == "teacher":
        teacher_profile = getattr(user, "teacher_profile", None)
        if not teacher_profile:
            return Notice.objects.none()
        school = teacher_profile.school
        my_classes = SchoolClass.objects.filter(class_teacher=teacher_profile)
        return (
            Notice.objects.filter(school=school)
            .filter(active_filter)
            .filter(Q(audience__in=["all", "teachers"]) | (Q(audience="classes") & Q(target_classes__in=my_classes)))
            .distinct()
        )

    if role == "parent":
        guardians = Guardian.objects.filter(user=user, link_status="approved")
        students = Student.objects.filter(student_guardians__guardian__in=guardians)
        schools = set(students.values_list("school_id", flat=True))
        classes = set(students.exclude(class_section__isnull=True).values_list("class_section_id", flat=True))

        return (
            Notice.objects.filter(school_id__in=schools)
            .filter(active_filter)
            .filter(Q(audience__in=["all", "parents"]) | (Q(audience="classes") & Q(target_classes__id__in=classes)))
            .distinct()
        )

    if role == "student":
        student_profile = getattr(user, "student_profile", None)
        if not student_profile:
            return Notice.objects.none()
        school = student_profile.school
        s_class = student_profile.class_section
        cond = Q(audience="all")
        if s_class:
            cond |= Q(audience="classes") & Q(target_classes=s_class)

        return (
            Notice.objects.filter(school=school)
            .filter(active_filter)
            .filter(cond)
            .distinct()
        )

    return Notice.objects.none()
