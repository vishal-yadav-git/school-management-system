from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from api.permissions import IsPrincipalOrSuperuser
from api.views_admin import get_principal_school, get_target_school
from audit.services import log_action
from .models import AcademicYear
from .serializers import AcademicYearSerializer


@api_view(["GET", "POST"])
@permission_classes([IsPrincipalOrSuperuser])
def academic_years(request):
    """
    GET /api/v1/academic-years/
    List academic years for the target school.

    POST /api/v1/academic-years/
    Create an academic year for the school.
    If isCurrent=True, any existing current year for this school is unset in the same transaction.
    Logs academic_year.create and optionally academic_year.set_current in AuditLog.
    """
    user = request.user
    if request.method == "GET":
        if user.is_superuser:
            school_id = request.query_params.get("school")
            if school_id:
                queryset = AcademicYear.objects.filter(school_id=school_id)
            else:
                queryset = AcademicYear.objects.all()
        else:
            school = get_principal_school(user)
            queryset = AcademicYear.objects.filter(school=school)

        serializer = AcademicYearSerializer(queryset, many=True)
        return Response(serializer.data)

    elif request.method == "POST":
        school = get_target_school(request)
        serializer = AcademicYearSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        name = serializer.validated_data["name"]
        start_date = serializer.validated_data["start_date"]
        end_date = serializer.validated_data["end_date"]
        is_current = serializer.validated_data.get("is_current", False)

        if AcademicYear.objects.filter(school=school, name=name).exists():
            return Response(
                {"name": ["Academic year with this name already exists for this school."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            prev_current = None
            if is_current:
                prev_current = AcademicYear.objects.filter(school=school, is_current=True).first()
                if prev_current:
                    prev_current.is_current = False
                    prev_current.save(update_fields=["is_current"])

            ay = AcademicYear.objects.create(
                school=school,
                name=name,
                start_date=start_date,
                end_date=end_date,
                is_current=is_current,
            )

            # Log creation
            log_action(
                actor=user,
                school=school,
                action="academic_year.create",
                obj=ay,
                changes={
                    "name": ay.name,
                    "startDate": str(ay.start_date),
                    "endDate": str(ay.end_date),
                    "isCurrent": ay.is_current,
                },
                request=request,
            )

            # If current year was set, log set_current
            if is_current:
                log_action(
                    actor=user,
                    school=school,
                    action="academic_year.set_current",
                    obj=ay,
                    changes={
                        "previousCurrentId": prev_current.id if prev_current else None,
                        "currentId": ay.id,
                        "name": ay.name,
                    },
                    request=request,
                )

        return Response(AcademicYearSerializer(ay).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsPrincipalOrSuperuser])
def academic_year_set_current(request, pk):
    """
    POST /api/v1/academic-years/<pk>/set-current/
    Sets this academic year as current for its school.
    Unsets any previous current year in the same transaction.
    Logs academic_year.set_current in AuditLog.
    """
    user = request.user
    if user.is_superuser:
        ay = get_object_or_404(AcademicYear, pk=pk)
        school = ay.school
    else:
        school = get_principal_school(user)
        ay = get_object_or_404(AcademicYear, pk=pk, school=school)

    if ay.is_current:
        return Response(AcademicYearSerializer(ay).data, status=status.HTTP_200_OK)

    with transaction.atomic():
        prev_current = AcademicYear.objects.filter(school=school, is_current=True).exclude(pk=ay.pk).first()
        if prev_current:
            prev_current.is_current = False
            prev_current.save(update_fields=["is_current"])

        ay.is_current = True
        ay.save(update_fields=["is_current"])

        log_action(
            actor=user,
            school=school,
            action="academic_year.set_current",
            obj=ay,
            changes={
                "previousCurrentId": prev_current.id if prev_current else None,
                "currentId": ay.id,
                "name": ay.name,
            },
            request=request,
        )

    return Response(AcademicYearSerializer(ay).data, status=status.HTTP_200_OK)
