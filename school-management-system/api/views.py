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
        data["teacher"] = {"employeeId": teacher.employee_id, "designation": teacher.designation}
    student = getattr(user, "student_profile", None)
    if student:
        c = student.class_section
        class_name = f"{c.name}-{c.section}" if c else None
        data["student"] = {
            "admissionNumber": student.admission_number,
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
