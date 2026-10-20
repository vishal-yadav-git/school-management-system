from datetime import datetime
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academics.models import SchoolClass, Student
from api.permissions import IsPrincipalOrSuperuser
from api.views_admin import get_principal_school
from guardians.models import Guardian
from .models import AttendanceRecord, AttendanceSession
from .serializers import AttendanceSessionInputSerializer
from .services import (
    get_class_attendance_roster,
    get_school_attendance_summary,
    get_school_attendance_trend,
    upsert_attendance_session,
)


def check_class_attendance_permission(user, school_class):
    if user.is_superuser:
        return True
    if getattr(user, "role", "") in ("principal", "admin"):
        school = get_principal_school(user)
        if school_class.school_id != school.id:
            raise PermissionDenied("You do not have access to classes of this school.")
        return True
    if getattr(user, "role", "") == "teacher":
        if not school_class.class_teacher or school_class.class_teacher.user_id != user.id:
            raise PermissionDenied("Only the designated class teacher can access this class's attendance.")
        return True
    raise PermissionDenied("You do not have permission to access attendance.")


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def class_attendance(request, class_id):
    """
    GET /api/v1/attendance/class/<classId>/?date=YYYY-MM-DD
    PUT /api/v1/attendance/class/<classId>/
    """
    school_class = get_object_or_404(SchoolClass, id=class_id)
    check_class_attendance_permission(request.user, school_class)

    if request.method == "GET":
        date_str = request.query_params.get("date")
        target_date = timezone.localdate()
        if date_str:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return Response({"date": ["Invalid date format. Expected YYYY-MM-DD."]}, status=status.HTTP_400_BAD_REQUEST)

        roster = get_class_attendance_roster(school_class, date=target_date)
        return Response(roster)

    elif request.method == "PUT":
        serializer = AttendanceSessionInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        session_date = serializer.validated_data["date"]
        records = serializer.validated_data["records"]

        try:
            upsert_attendance_session(
                school_class=school_class,
                date=session_date,
                records_data=records,
                actor=request.user,
                request=request,
            )
        except ValidationError as e:
            return Response(getattr(e, "message_dict", {"detail": str(e)}), status=status.HTTP_400_BAD_REQUEST)

        roster = get_class_attendance_roster(school_class, date=session_date)
        return Response(roster, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsPrincipalOrSuperuser])
def attendance_summary(request):
    """
    GET /api/v1/attendance/summary/?date=YYYY-MM-DD
    Principal views own school summary; superuser can view ?school=<id>.
    """
    user = request.user
    if user.is_superuser:
        school_id = request.query_params.get("school")
        from schools.models import School
        school = get_object_or_404(School, id=school_id) if school_id else School.objects.first()
    else:
        school = get_principal_school(user)

    date_str = request.query_params.get("date")
    target_date = timezone.localdate()
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"date": ["Invalid date format. Expected YYYY-MM-DD."]}, status=status.HTTP_400_BAD_REQUEST)

    summary = get_school_attendance_summary(school, date=target_date)
    return Response(summary)


@api_view(["GET"])
@permission_classes([IsPrincipalOrSuperuser])
def attendance_trend(request):
    """
    GET /api/v1/attendance/trend/?days=7
    """
    user = request.user
    if user.is_superuser:
        school_id = request.query_params.get("school")
        from schools.models import School
        school = get_object_or_404(School, id=school_id) if school_id else School.objects.first()
    else:
        school = get_principal_school(user)

    try:
        days = int(request.query_params.get("days", 7))
        days = max(1, min(days, 30))
    except (ValueError, TypeError):
        days = 7

    trend = get_school_attendance_trend(school, days=days)
    return Response(trend)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_attendance(request, student_id):
    """
    GET /api/v1/attendance/student/<studentId>/?month=YYYY-MM
    Allowed for: principal of school, class teacher, the student themself, or approved parent.
    """
    student = get_object_or_404(Student, id=student_id)
    user = request.user

    allowed = False
    if user.is_superuser:
        allowed = True
    elif getattr(user, "role", "") in ("principal", "admin"):
        school = get_principal_school(user)
        if student.school_id == school.id:
            allowed = True
    elif getattr(user, "role", "") == "teacher":
        if student.class_section and student.class_section.class_teacher and student.class_section.class_teacher.user_id == user.id:
            allowed = True
    elif getattr(user, "role", "") == "student":
        if student.user_id == user.id:
            allowed = True
    elif getattr(user, "role", "") == "parent":
        # Check approved guardian link
        if Guardian.objects.filter(user=user, link_status="approved", guardian_students__student=student).exists():
            allowed = True

    if not allowed:
        raise PermissionDenied("You do not have permission to view attendance for this student.")

    month_str = request.query_params.get("month")
    today = timezone.localdate()
    if month_str:
        try:
            m_date = datetime.strptime(month_str, "%Y-%m").date()
            year = m_date.year
            month = m_date.month
        except ValueError:
            return Response({"month": ["Invalid month format. Expected YYYY-MM."]}, status=status.HTTP_400_BAD_REQUEST)
    else:
        year = today.year
        month = today.month

    records = AttendanceRecord.objects.filter(
        student=student,
        session__date__year=year,
        session__date__month=month,
    ).select_related("session").order_by("session__date")

    days_data = []
    p_count = 0
    a_count = 0
    late_count = 0
    leave_count = 0

    for r in records:
        d_str = str(r.session.date)
        days_data.append({"date": d_str, "status": r.status, "remark": r.remark})
        if r.status == "present":
            p_count += 1
        elif r.status == "absent":
            a_count += 1
        elif r.status == "late":
            late_count += 1
        elif r.status == "leave":
            leave_count += 1

    total = len(days_data)
    present_percent = round(((p_count + late_count) / total * 100), 1) if total > 0 else 0.0

    return Response({
        "studentId": student.id,
        "name": student.user.get_full_name() or student.user.username,
        "month": f"{year:04d}-{month:02d}",
        "days": days_data,
        "stats": {
            "totalDays": total,
            "present": p_count,
            "absent": a_count,
            "late": late_count,
            "leave": leave_count,
            "presentPercent": present_percent,
        },
    })
