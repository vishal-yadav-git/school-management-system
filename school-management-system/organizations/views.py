from django.contrib.auth import login
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from academic_year.models import AcademicYear
from academics.models import SchoolClass, Student, Teacher
from api.serializers import ClassSerializer, SchoolSerializer, UserSerializer
from audit.services import log_action

from .models import OrganizationMember, SchoolOrganization
from .serializers import CampusSerializer, OrganizationSerializer, RegisterOrgSerializer
from .services import (
    create_organization_with_campus,
    get_active_school_for_user,
    switch_active_campus,
    verify_email_token,
)


class RegisterOrgThrottle(SimpleRateThrottle):
    scope = "register_org"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegisterOrgThrottle])
def register_org(request):
    serializer = RegisterOrgSerializer(data=request.data)
    if not serializer.is_valid():
        errs = serializer.errors
        if "detail" in errs:
            val = errs["detail"]
            msg = val[0] if isinstance(val, list) and val else str(val)
            return Response({"detail": str(msg)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(errs, status=status.HTTP_400_BAD_REQUEST)

    user, org, school, _ = create_organization_with_campus(serializer.validated_data)

    return Response(
        {
            "detail": "Organization registered successfully. Please verify your email to activate full institutional features.",
            "organization": OrganizationSerializer(org).data,
            "school": SchoolSerializer(school).data,
            "status": "pending",
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_email(request):
    token = request.query_params.get("token", "").strip()
    if not token:
        return Response({"detail": "Verification token is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = verify_email_token(token)
    except ValidationError as e:
        return Response({"detail": str(e.message if hasattr(e, "message") else e)}, status=status.HTTP_400_BAD_REQUEST)

    login(request, user)
    request.session.set_expiry(14 * 24 * 60 * 60)

    active_school = get_active_school_for_user(request)
    return Response(
        {
            "detail": "Email verified successfully. Your campus is now active.",
            "user": UserSerializer(user).data,
            "school": SchoolSerializer(active_school).data if active_school else None,
            "status": "active",
            "redirectUrl": "/admin",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def campuses_list(request):
    user = request.user
    if user.is_superuser:
        campuses = SchoolOrganization.objects.all().select_related("school", "organization")
    else:
        user_org_ids = OrganizationMember.objects.filter(
            user=user,
            role__in=["owner", "admin", "viewer"],
        ).values_list("organization_id", flat=True)
        campuses = SchoolOrganization.objects.filter(
            organization_id__in=user_org_ids,
        ).select_related("school", "organization")

    serializer = CampusSerializer(campuses, many=True, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def switch_campus(request):
    school_id = request.data.get("schoolId")
    if not school_id:
        return Response({"schoolId": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)

    try:
        school = switch_active_campus(request.user, school_id, request=request)
    except PermissionDenied as e:
        return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
    except ValidationError as e:
        return Response({"detail": str(e.message if hasattr(e, "message") else e)}, status=status.HTTP_400_BAD_REQUEST)

    # Return updated active school payload
    return Response(
        {
            "detail": f"Switched to campus: {school.name}",
            "activeSchool": SchoolSerializer(school).data,
            "schoolId": school.id,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def setup_status(request):
    school = get_active_school_for_user(request)
    if not school:
        raise PermissionDenied("User is not associated with an institute.")

    # Check school verification status
    so = SchoolOrganization.objects.filter(school=school).first()
    school_status = so.status if so else "active"

    # Compute step completions
    ay_count = AcademicYear.objects.filter(school=school).count()
    ay_current = AcademicYear.objects.filter(school=school, is_current=True).exists()

    classes_count = SchoolClass.objects.filter(school=school).count()
    teachers_count = Teacher.objects.filter(school=school).count()
    students_count = Student.objects.filter(school=school).count()

    checklist = {
        "academicYear": {
            "completed": ay_current,
            "count": ay_count,
            "label": "Academic Year Configured",
        },
        "classes": {
            "completed": classes_count > 0,
            "count": classes_count,
            "label": "Classes & Sections Added",
        },
        "teachers": {
            "completed": teachers_count > 0,
            "count": teachers_count,
            "label": "Teachers Added",
        },
        "students": {
            "completed": students_count > 0,
            "count": students_count,
            "label": "Students Enrolled",
        },
    }

    completed_steps = sum(1 for item in checklist.values() if item["completed"])
    overall_progress = int((completed_steps / 4.0) * 100)

    return Response(
        {
            "schoolId": school.id,
            "schoolName": school.name,
            "status": school_status,
            "overallProgress": overall_progress,
            "checklist": checklist,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def principal_classes(request):
    user = request.user
    if not (user.is_superuser or getattr(user, "role", "") in ("admin", "principal")):
        raise PermissionDenied("Only principals and administrators can manage classes.")

    school = get_active_school_for_user(request)
    if not school:
        raise PermissionDenied("User is not associated with an institute.")

    if request.method == "GET":
        classes = SchoolClass.objects.filter(school=school).select_related("class_teacher__user").order_by("name", "section")
        return Response(ClassSerializer(classes, many=True).data, status=status.HTTP_200_OK)

    elif request.method == "POST":
        name = request.data.get("name", "").strip()
        section = request.data.get("section", "").strip()
        if not name or not section:
            return Response(
                {"detail": "Both class name and section are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if SchoolClass.objects.filter(school=school, name__iexact=name, section__iexact=section).exists():
            return Response(
                {"detail": f"Class {name}-{section} already exists in this school."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        school_class = SchoolClass.objects.create(
            school=school,
            name=name,
            section=section,
        )

        log_action(
            actor=user,
            school=school,
            action="class.create",
            obj=school_class,
            changes={"name": name, "section": section},
            request=request,
        )

        return Response(ClassSerializer(school_class).data, status=status.HTTP_201_CREATED)
