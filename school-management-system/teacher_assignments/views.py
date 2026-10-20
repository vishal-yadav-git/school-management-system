from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from academics.models import SchoolClass, Subject, Teacher
from api.permissions import IsPrincipalOrSuperuser
from organizations.services import get_active_school_for_user

from .models import ClassSubjectTeacher, TeacherPermission
from .serializers import (
    AssignSubjectTeacherInputSerializer,
    ClassSubjectTeacherSerializer,
    GrantPermissionInputSerializer,
    TeacherPermissionSerializer,
)
from .services import assign_class_subject_teacher, grant_permission, revoke_permission


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
