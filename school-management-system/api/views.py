from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from academics.models import SchoolClass, Student, Subject, Teacher
from accounts.models import User
from schools.models import School

from .permissions import IsPrincipalOrSuperuser, IsStudent, IsTeacher
from .serializers import (
    ClassSerializer,
    RegisterSerializer,
    SchoolSerializer,
    StudentSerializer,
    TeacherSerializer,
    UserSerializer,
)

REDIRECTS = {
    "admin": "/admin",
    "principal": "/admin",
    "teacher": "/teacher/attendance",
    "parent": "/parent",
    "student": "/student",
}


def user_school(user):
    principal_school = getattr(user, "principal_school", None)
    if principal_school:
        return principal_school
    for rel in ("teacher_profile", "student_profile"):
        profile = getattr(user, rel, None)
        if profile and hasattr(profile, "school"):
            return profile.school
    return None


def scoped(qs, user, request=None):
    if user.is_superuser:
        return qs
    school = getattr(user, "principal_school", None)
    if not school and request:
        try:
            from organizations.services import get_active_school_for_user
            school = get_active_school_for_user(request)
        except ImportError:
            pass
    return qs.filter(school=school) if school else qs.none()


def session_payload(user):
    school = user_school(user)
    data = {
        "user": UserSerializer(user).data,
        "school": SchoolSerializer(school).data if school else None,
        "redirectUrl": "/admin" if (user.is_superuser or getattr(user, "role", "") in ("admin", "principal")) else REDIRECTS.get(user.role, "/"),
    }
    teacher = getattr(user, "teacher_profile", None)
    if teacher:
        val = teacher.employee_id or ""
        code = teacher.school.code if teacher.school else ""
        prefix = f"{code}-"
        display_eid = val[len(prefix):] if (code and val.startswith(prefix)) else val
        data["teacher"] = {"employeeId": display_eid, "designation": teacher.designation}
    student = getattr(user, "student_profile", None)
    if student:
        c = student.class_section
        class_name = f"{c.name}-{c.section}" if c else None
        val = student.admission_number or ""
        code = student.school.code if student.school else ""
        prefix = f"{code}-"
        display_adm = val[len(prefix):] if (code and val.startswith(prefix)) else val
        data["student"] = {
            "id": student.id,
            "admissionNumber": display_adm,
            "className": class_name,
        }
    return data



class AuthThrottle(SimpleRateThrottle):
    scope = "auth"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    token = get_token(request)
    response = Response({"csrfToken": token})
    # Ensure cookie is explicitly populated on the response
    response.set_cookie("csrftoken", token, samesite="Lax")
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def login_view(request):
    username = request.data.get("username", "")
    password = request.data.get("password")

    if isinstance(username, str):
        username = username.strip()

    lookup_user = User.objects.filter(username__iexact=username).first()
    if not lookup_user and username:
        lookup_user = User.objects.filter(email__iexact=username).first()
    if not lookup_user and username:
        lookup_user = User.objects.filter(mobile=username).first()

    auth_username = lookup_user.username if lookup_user else username

    user = authenticate(request, username=auth_username, password=password)
    if user is None:
        return Response({"detail": "Invalid username or password"}, status=400)

    login(request, user)
    remember = request.data.get("remember", True)
    if remember is False or str(remember).lower() in ["false", "0"]:
        request.session.set_expiry(0)
    else:
        request.session.set_expiry(14 * 24 * 60 * 60)
    return Response(session_payload(user))




@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    user = serializer.save()
    login(request, user)
    return Response(session_payload(user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response({"detail": "Logged out successfully"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(session_payload(request.user))


@api_view(["GET"])
@permission_classes([AllowAny])
def schools(request):
    qs = School.objects.order_by("name")
    search = request.query_params.get("search")
    city = request.query_params.get("city")
    if search:
        qs = qs.filter(name__icontains=search)
    if city:
        qs = qs.filter(city__iexact=city)
    return Response(SchoolSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def school_detail(request, pk):
    return Response(SchoolSerializer(get_object_or_404(School, pk=pk)).data)


@api_view(["GET"])
@permission_classes([IsPrincipalOrSuperuser])
def dashboard_stats(request):
    u = request.user
    from organizations.services import get_active_school_for_user
    active_school = get_active_school_for_user(request) or user_school(u)

    if not u.is_superuser and active_school:
        so = getattr(active_school, "organization_membership", None)
        if so and so.status == "pending":
            return Response(
                {
                    "detail": "School email verification is pending. Please verify your email before accessing the dashboard.",
                    "code": "EMAIL_VERIFICATION_PENDING",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

    data = {
        "totalTeachers": scoped(Teacher.objects.all(), u, request).count(),
        "totalStudents": scoped(Student.objects.all(), u, request).count(),
        "totalClasses": scoped(SchoolClass.objects.all(), u, request).count(),
        "totalSubjects": scoped(Subject.objects.all(), u, request).count(),
    }
    if u.is_superuser:
        data["totalSchools"] = School.objects.count()
        data["totalPrincipals"] = User.objects.filter(role="principal").count()
    return Response(data)


@api_view(["GET"])
@permission_classes([IsPrincipalOrSuperuser])
def classes(request):
    qs = scoped(SchoolClass.objects.all(), request.user)
    return Response(ClassSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsPrincipalOrSuperuser])
def teachers(request):
    qs = scoped(Teacher.objects.select_related("user"), request.user)
    return Response(TeacherSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsPrincipalOrSuperuser])
def students(request):
    qs = scoped(Student.objects.select_related("user", "class_section"), request.user)
    return Response(StudentSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsTeacher])
def my_students(request):
    teacher = getattr(request.user, "teacher_profile", None)
    classes_qs = SchoolClass.objects.filter(class_teacher=teacher) if teacher else SchoolClass.objects.none()
    students_qs = Student.objects.filter(class_section__in=classes_qs).select_related("user", "class_section")
    return Response(
        {
            "classes": ClassSerializer(classes_qs, many=True).data,
            "students": StudentSerializer(students_qs, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsStudent])
def student_me(request):
    u = request.user
    profile = getattr(u, "student_profile", None)
    if not profile and u.is_superuser:
        profile = Student.objects.select_related("user", "school", "class_section").first()
    if not profile:
        return Response({"detail": "Student profile not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(StudentSerializer(profile).data)


@api_view(["GET"])
@permission_classes([IsPrincipalOrSuperuser])
def dashboard_summary(request):
    u = request.user
    from organizations.services import get_active_school_for_user
    active_school = get_active_school_for_user(request) or user_school(u)

    if u.is_superuser:
        school_id = request.query_params.get("school")
        if school_id:
            active_school = get_object_or_404(School, pk=school_id)
        elif not active_school:
            active_school = School.objects.first()

    if not active_school:
        return Response({"detail": "No active school found for your account."}, status=status.HTTP_400_BAD_REQUEST)

    if not u.is_superuser and active_school:
        so = getattr(active_school, "organization_membership", None)
        if so and so.status == "pending":
            return Response(
                {
                    "detail": "School email verification is pending. Please verify your email before accessing the dashboard.",
                    "code": "EMAIL_VERIFICATION_PENDING",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

    from django.db.models import Count, Q
    from django.utils import timezone
    from academic_year.models import AcademicYear
    from attendance.models import AttendanceSession, AttendanceRecord
    from guardians.models import Guardian

    today = timezone.localdate()

    # Core Counts (aggregate & counts)
    total_students = Student.objects.filter(school=active_school).count()
    total_teachers = Teacher.objects.filter(school=active_school).count()
    total_classes = SchoolClass.objects.filter(school=active_school).count()
    total_subjects = Subject.objects.filter(school=active_school).count()

    # Active Academic Year
    ay = AcademicYear.objects.filter(school=active_school, is_current=True).first()
    if not ay:
        ay = AcademicYear.objects.filter(school=active_school).order_by("-start_date").first()

    ay_data = None
    if ay:
        ay_data = {
            "id": ay.id,
            "name": ay.name,
            "startDate": str(ay.start_date),
            "endDate": str(ay.end_date),
            "isCurrent": ay.is_current,
        }

    # Attendance Today (Plan Addition C: "Not taken yet" when 0 marked classes)
    sessions = AttendanceSession.objects.filter(school=active_school, date=today)
    marked_classes = sessions.count()
    not_taken_classes = max(0, total_classes - marked_classes)

    present_pct = None
    if marked_classes > 0:
        rec_agg = AttendanceRecord.objects.filter(session__in=sessions).aggregate(
            total=Count("id"),
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
        )
        marked_students = rec_agg["total"] or 0
        present_cnt = rec_agg["present"] or 0
        present_pct = round((present_cnt / marked_students) * 100, 1) if marked_students > 0 else 0.0

    # Pending Guardian Requests
    pending_guardians = Guardian.objects.filter(school=active_school, link_status="pending").count()

    # Setup Status
    ay_current = bool(ay and ay.is_current)
    completed_steps = (1 if ay_current else 0) + (1 if total_classes > 0 else 0) + (1 if total_teachers > 0 else 0) + (1 if total_students > 0 else 0)
    overall_progress = int((completed_steps / 4.0) * 100)

    data = {
        "school": {
            "id": active_school.id,
            "name": active_school.name,
            "code": active_school.code,
        },
        "totalStudents": total_students,
        "totalTeachers": total_teachers,
        "classesTotal": total_classes,
        "classesTaken": marked_classes,
        "classesNotTaken": not_taken_classes,
        "presentToday": {
            "taken": marked_classes > 0,
            "percent": present_pct,
        },
        "pendingGuardianRequests": pending_guardians,
        "currentAcademicYear": ay_data,
        "setupProgress": {
            "overallProgress": overall_progress,
            "isComplete": overall_progress == 100,
        },
    }
    return Response(data)


@api_view(["GET"])
@permission_classes([IsTeacher])
def teacher_my_classes(request):
    """
    GET /api/v1/teacher/my-classes/
    Returns unified classes for the teacher:
    - Designated Class Teacher classes (role="class_teacher", canMarkAttendance=True)
    - Subject Teacher classes (role="subject_teacher", canMarkAttendance=False, syllabus-only)
    - Granular teacher permissions
    - Active Academic Year date bounds
    """
    teacher = getattr(request.user, "teacher_profile", None)
    if not teacher:
        return Response({"detail": "Teacher profile not found."}, status=status.HTTP_404_NOT_FOUND)

    school = teacher.school

    from teacher_assignments.models import ClassSubjectTeacher, TeacherPermission
    from academic_year.models import AcademicYear

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


@api_view(["DELETE"])
@permission_classes([IsPrincipalOrSuperuser])
def class_subject_teacher_delete_view(request, class_id, mapping_id):
    """
    DELETE /api/v1/classes/<class_id>/subject-teachers/<mapping_id>/
    Principal removes a subject teacher mapping.
    """
    from organizations.services import get_active_school_for_user
    active_school = get_active_school_for_user(request)
    school_class = get_object_or_404(SchoolClass, pk=class_id)

    if not request.user.is_superuser and active_school and school_class.school_id != active_school.id:
        return Response({"detail": "Class does not belong to your school."}, status=status.HTTP_403_FORBIDDEN)

    target_school = active_school or school_class.school

    from teacher_assignments.services import unassign_class_subject_teacher
    from django.core.exceptions import ValidationError as DjangoValidationError

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



