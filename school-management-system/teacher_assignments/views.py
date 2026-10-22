from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from academics.models import SchoolClass, Subject, Teacher
from academic_year.models import AcademicYear
from api.permissions import IsPrincipalOrSuperuser, IsTeacher
from organizations.services import get_active_school_for_user

from .models import ClassSubjectTeacher, TeacherPermission
from .serializers import (
    AssignSubjectTeacherInputSerializer,
    ClassSubjectTeacherSerializer,
    GrantPermissionInputSerializer,
    TeacherPermissionSerializer,
)
from .services import (
    assign_class_subject_teacher,
    grant_permission,
    revoke_permission,
    unassign_class_subject_teacher,
)


@api_view(["GET", "POST"])
@permission_classes([IsPrincipalOrSuperuser])
def teacher_permissions_view(request, teacher_id):
    """
    GET /api/v1/teachers/<id>/permissions/
    POST /api/v1/teachers/<id>/permissions/
    Principal manages granular permissions for a teacher in their school.
    """
    active_school = get_active_school_for_user(request)
    if not active_school and not request.user.is_superuser:
        return Response({"detail": "No active school found for your account."}, status=status.HTTP_400_BAD_REQUEST)

    teacher = get_object_or_404(Teacher, pk=teacher_id)
    if not request.user.is_superuser and teacher.school_id != active_school.id:
        return Response({"detail": "Teacher does not belong to your school."}, status=status.HTTP_403_FORBIDDEN)

    target_school = active_school or teacher.school

    if request.method == "GET":
        perms = TeacherPermission.objects.filter(school=target_school, teacher=teacher)
        return Response(TeacherPermissionSerializer(perms, many=True).data)

    elif request.method == "POST":
        serializer = GrantPermissionInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        key = serializer.validated_data["permissionKey"]
        granted = serializer.validated_data["granted"]

        try:
            if granted:
                grant_permission(
                    school=target_school,
                    teacher=teacher,
                    permission_key=key,
                    actor=request.user,
                    request=request,
                )
            else:
                revoke_permission(
                    school=target_school,
                    teacher=teacher,
                    permission_key=key,
                    actor=request.user,
                    request=request,
                )
        except DjangoValidationError as exc:
            msg = exc.messages if hasattr(exc, "messages") else str(exc)
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        # Return updated list
        perms = TeacherPermission.objects.filter(school=target_school, teacher=teacher)
        return Response(TeacherPermissionSerializer(perms, many=True).data, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
def class_subject_teachers_view(request, class_id):
    """
    GET /api/v1/classes/<id>/subject-teachers/
    POST /api/v1/classes/<id>/subject-teachers/
    """
    active_school = get_active_school_for_user(request)
    school_class = get_object_or_404(SchoolClass, pk=class_id)

    if not request.user.is_superuser and active_school and school_class.school_id != active_school.id:
        return Response({"detail": "Class does not belong to your school."}, status=status.HTTP_403_FORBIDDEN)

    target_school = active_school or school_class.school

    if request.method == "GET":
        mappings = ClassSubjectTeacher.objects.filter(school_class=school_class).select_related("subject", "teacher__user", "school_class")
        return Response(ClassSubjectTeacherSerializer(mappings, many=True).data)

    elif request.method == "POST":
        # Only Principal or Superuser can map subject teachers
        if not (request.user.is_superuser or getattr(request.user, "role", "") in ("principal", "admin")):
            return Response({"detail": "Only principals can assign subject teachers."}, status=status.HTTP_403_FORBIDDEN)

        serializer = AssignSubjectTeacherInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        subject = get_object_or_404(Subject, pk=serializer.validated_data["subjectId"])
        teacher = get_object_or_404(Teacher, pk=serializer.validated_data["teacherId"])

        try:
            cst = assign_class_subject_teacher(
                school=target_school,
                school_class=school_class,
                subject=subject,
                teacher=teacher,
                actor=request.user,
                request=request,
            )
        except DjangoValidationError as exc:
            msg = exc.messages if hasattr(exc, "messages") else str(exc)
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ClassSubjectTeacherSerializer(cst).data, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsPrincipalOrSuperuser])
def class_subject_teacher_delete_view(request, class_id, mapping_id):
    """
    DELETE /api/v1/classes/<class_id>/subject-teachers/<mapping_id>/
    Principal removes a subject teacher mapping.
    """
    active_school = get_active_school_for_user(request)
    school_class = get_object_or_404(SchoolClass, pk=class_id)

    if not request.user.is_superuser and active_school and school_class.school_id != active_school.id:
        return Response({"detail": "Class does not belong to your school."}, status=status.HTTP_403_FORBIDDEN)

    target_school = active_school or school_class.school

    try:
        unassign_class_subject_teacher(
            school=target_school,
            mapping_id=mapping_id,
            actor=request.user,
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
    except DjangoValidationError as exc:
        msg = exc.messages if hasattr(exc, "messages") else str(exc)
        return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsTeacher])
def teacher_my_classes(request):
    """
    GET /api/v1/teacher/my-classes/
    Returns unified classes for the teacher:
    - Designated Class Teacher classes (canTakeAttendance=True)
    - Subject Teacher classes (canTakeAttendance=False, syllabus-only)
    - Granular teacher permissions
    - Active Academic Year date bounds
    """
    teacher = getattr(request.user, "teacher_profile", None)
    if not teacher:
        return Response({"detail": "Teacher profile not found."}, status=status.HTTP_404_NOT_FOUND)

    school = teacher.school

    # 1. Designated class teacher classes
    ct_class_ids = set(SchoolClass.objects.filter(class_teacher=teacher).values_list("id", flat=True))

    # 2. Subject teacher mappings
    st_mappings = ClassSubjectTeacher.objects.filter(teacher=teacher).select_related("school_class", "subject")

    class_subjects_map = {}
    st_class_ids = set()
    for m in st_mappings:
        st_class_ids.add(m.school_class_id)
        if m.school_class_id not in class_subjects_map:
            class_subjects_map[m.school_class_id] = []
        class_subjects_map[m.school_class_id].append({
            "id": m.subject.id,
            "name": m.subject.name,
            "code": m.subject.code,
        })

    all_class_ids = ct_class_ids | st_class_ids
    classes_qs = SchoolClass.objects.filter(id__in=all_class_ids).order_by("name", "section").prefetch_related("students")

    classes_data = []
    for c in classes_qs:
        is_ct = (c.id in ct_class_ids)
        # Plan Addition A: Attendance permission is strictly class-teacher-only!
        classes_data.append({
            "id": c.id,
            "name": c.name,
            "section": c.section,
            "displayName": f"Class {c.name}-{c.section}",
            "role": "class_teacher" if is_ct else "subject_teacher",
            "isClassTeacher": is_ct,
            "canMarkAttendance": is_ct,
            "canTakeAttendance": is_ct,
            "totalStudents": c.students.count(),
            "subjects": class_subjects_map.get(c.id, []),
        })

    perms = list(TeacherPermission.objects.filter(teacher=teacher).values_list("permission_key", flat=True))

    ay = AcademicYear.objects.filter(school=school, is_current=True).first()
    if not ay:
        ay = AcademicYear.objects.filter(school=school).order_by("-start_date").first()

    ay_data = None
    if ay:
        ay_data = {
            "id": ay.id,
            "name": ay.name,
            "startDate": str(ay.start_date),
            "endDate": str(ay.end_date),
        }

    return Response({
        "teacher": {
            "id": teacher.id,
            "name": request.user.get_full_name() or request.user.username,
            "employeeId": teacher.employee_id,
        },
        "permissions": perms,
        "currentAcademicYear": ay_data,
        "academicYear": ay_data,
        "classes": classes_data,
    })


