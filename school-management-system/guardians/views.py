from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from academics.models import Student
from api.permissions import IsParent, IsPrincipalOrSuperuser
from api.views_admin import get_principal_school
from .models import Guardian, StudentGuardian
from .serializers import (
    AddGuardianSerializer,
    GuardianLinkRequestSerializer,
    ParentChildSerializer,
    StudentGuardianSerializer,
)
from .services import (
    add_student_guardian,
    approve_guardian_link,
    claim_guardians_for_parent,
    reject_guardian_link,
    remove_student_guardian,
)


class GuardianClaimThrottle(ScopedRateThrottle):
    scope = "guardian_claim"


@api_view(["GET", "POST"])
@permission_classes([IsPrincipalOrSuperuser])
def student_guardians(request, pk):
    """
    GET /api/v1/students/<id>/guardians/
    POST /api/v1/students/<id>/guardians/
    """
    student = get_object_or_404(Student, id=pk)
    if not request.user.is_superuser:
        school = get_principal_school(request.user)
        if student.school_id != school.id:
            raise PermissionDenied("You do not have access to students of this school.")

    if request.method == "GET":
        sg_list = StudentGuardian.objects.filter(student=student).select_related("guardian", "guardian__user")
        serializer = StudentGuardianSerializer(sg_list, many=True)
        return Response(serializer.data)

    elif request.method == "POST":
        serializer = AddGuardianSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            sg = add_student_guardian(
                student=student,
                full_name=serializer.validated_data["fullName"],
                mobile=serializer.validated_data["mobile"],
                relation=serializer.validated_data.get("relation", "guardian"),
                is_primary=serializer.validated_data.get("isPrimary", False),
                email=serializer.validated_data.get("email", ""),
                actor=request.user,
                request=request,
            )
        except ValidationError as e:
            return Response(getattr(e, "message_dict", {"detail": str(e)}), status=status.HTTP_400_BAD_REQUEST)

        return Response(StudentGuardianSerializer(sg).data, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsPrincipalOrSuperuser])
def student_guardian_delete(request, pk, guardian_id):
    """
    DELETE /api/v1/students/<id>/guardians/<guardianId>/
    """
    student = get_object_or_404(Student, id=pk)
    if not request.user.is_superuser:
        school = get_principal_school(request.user)
        if student.school_id != school.id:
            raise PermissionDenied("You do not have access to students of this school.")

    removed = remove_student_guardian(student, guardian_id, actor=request.user, request=request)
    if not removed:
        return Response({"detail": "Guardian link not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response({"detail": "Guardian link removed."}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsParent])
@throttle_classes([GuardianClaimThrottle])
def guardian_claim(request):
    """
    POST /api/v1/guardians/claim/
    Reads request.user.mobile only. Returns 400 if empty.
    """
    try:
        res = claim_guardians_for_parent(request.user, request=request)
    except ValidationError as e:
        msg = e.message if hasattr(e, "message") else str(e)
        if hasattr(e, "messages") and e.messages:
            msg = e.messages[0]
        return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    return Response(res, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsPrincipalOrSuperuser])
def guardian_link_requests(request):
    """
    GET /api/v1/guardians/link-requests/
    List pending claims for the principal's school.
    """
    if request.user.is_superuser:
        school_id = request.query_params.get("school")
        if school_id:
            qs = Guardian.objects.filter(school_id=school_id, link_status="pending")
        else:
            qs = Guardian.objects.filter(link_status="pending")
    else:
        school = get_principal_school(request.user)
        qs = Guardian.objects.filter(school=school, link_status="pending")

    qs = qs.select_related("requested_user").prefetch_related("guardian_students__student__user", "guardian_students__student__class_section")
    serializer = GuardianLinkRequestSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsPrincipalOrSuperuser])
def guardian_approve(request, guardian_id):
    """
    POST /api/v1/guardians/link-requests/<guardianId>/approve/
    """
    guardian = get_object_or_404(Guardian, id=guardian_id)
    if not request.user.is_superuser:
        school = get_principal_school(request.user)
        if guardian.school_id != school.id:
            raise PermissionDenied("You do not have permission for this school.")

    try:
        approve_guardian_link(guardian, principal=request.user, request=request)
    except ValidationError as e:
        msg = e.message if hasattr(e, "message") else str(e)
        return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"detail": "Link request approved."}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsPrincipalOrSuperuser])
def guardian_reject(request, guardian_id):
    """
    POST /api/v1/guardians/link-requests/<guardianId>/reject/
    """
    guardian = get_object_or_404(Guardian, id=guardian_id)
    if not request.user.is_superuser:
        school = get_principal_school(request.user)
        if guardian.school_id != school.id:
            raise PermissionDenied("You do not have permission for this school.")

    try:
        reject_guardian_link(guardian, principal=request.user, request=request)
    except ValidationError as e:
        msg = e.message if hasattr(e, "message") else str(e)
        return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"detail": "Link request rejected."}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsParent])
def parent_children(request):
    """
    GET /api/v1/parent/children/
    Lists approved children for the requesting parent user.
    """
    user = request.user
    # Find approved guardians linked to this user
    guardians = Guardian.objects.filter(user=user, link_status="approved")
    sg_list = StudentGuardian.objects.filter(guardian__in=guardians).select_related(
        "student",
        "student__user",
        "student__school",
        "student__class_section",
    )

    seen_students = set()
    children_data = []

    # Check today's attendance if attendance session exists
    today = timezone.localdate()

    for sg in sg_list:
        student = sg.student
        if student.id in seen_students:
            continue
        seen_students.add(student.id)

        c_name = f"{student.class_section.name}-{student.class_section.section}" if student.class_section else "Unassigned"

        # Check today's status from attendance app if available
        today_status = "present"
        try:
            from attendance.models import AttendanceRecord
            rec = AttendanceRecord.objects.filter(
                session__school_class=student.class_section,
                session__date=today,
                student=student,
            ).first()
            if rec:
                today_status = rec.status
        except Exception:
            pass

        children_data.append({
            "id": student.id,
            "name": student.user.get_full_name() or student.user.username,
            "admissionNumber": student.admission_number,
            "schoolId": student.school_id,
            "schoolName": student.school.name,
            "className": c_name,
            "todayStatus": today_status,
        })

    serializer = ParentChildSerializer(children_data, many=True)
    return Response(serializer.data)
