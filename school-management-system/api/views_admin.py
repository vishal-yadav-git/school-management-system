import os
import uuid
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from academics.models import SchoolClass, Student, Teacher
from accounts.models import User
from imports.views import (
    clean_value,
    convert_date,
    read_uploaded_file,
    split_name,
)
from schools.models import School

from .pagination import StandardResultsSetPagination
from .permissions import IsPrincipalOrSuperuser, IsSuperuserOnly
from .serializers import (
    ClassSerializer,
    PrincipalSerializer,
    SchoolSerializer,
    StudentSerializer,
    TeacherSerializer,
)


class AdminWriteThrottle(UserRateThrottle):
    rate = "60/minute"


class ImportUploadThrottle(UserRateThrottle):
    rate = "10/minute"


def get_principal_school(user):
    """
    Returns the school bound to this principal/user.
    Raises PermissionDenied if principal has no linked school.
    """
    if user.is_superuser:
        return None
    school = getattr(user, "principal_school", None)
    if not school:
        raise PermissionDenied("User is not associated with an institute.")
    return school


def get_target_school(request):
    """
    For superuser: can specify ?school=<id> or defaults to first school.
    For principal: strictly forced to user.principal_school.
    """
    u = request.user
    if u.is_superuser:
        school_id = request.data.get("school") or request.query_params.get("school")
        if school_id:
            return get_object_or_404(School, id=school_id)
        # default to first school if available
        first = School.objects.first()
        if not first:
            raise NotFound("No schools found in the system.")
        return first
    return get_principal_school(u)


# ==============================================================================
# 1. CLASSES CRUD
# ==============================================================================

@api_view(["GET", "POST"])
@permission_classes([IsPrincipalOrSuperuser])
@throttle_classes([AdminWriteThrottle])
def admin_classes(request):
    u = request.user
    if request.method == "GET":
        qs = SchoolClass.objects.select_related("school", "class_teacher", "class_teacher__user")
        if not u.is_superuser:
            school = get_principal_school(u)
            qs = qs.filter(school=school)
        else:
            school_filter = request.query_params.get("school")
            if school_filter:
                qs = qs.filter(school_id=school_filter)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(section__icontains=search)

        qs = qs.order_by("name", "section")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ClassSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    elif request.method == "POST":
        data = request.data
        name = clean_value(data.get("name"))
        section = clean_value(data.get("section"))
        teacher_id = data.get("classTeacher") or data.get("class_teacher")

        errors = {}
        if not name:
            errors["name"] = ["Class name/standard is required."]
        if not section:
            errors["section"] = ["Class section is required."]

        school = get_target_school(request)

        class_teacher = None
        if teacher_id:
            try:
                class_teacher = Teacher.objects.get(id=teacher_id, school=school)
            except Teacher.DoesNotExist:
                errors["classTeacher"] = ["Selected teacher does not belong to this institute."]

        if SchoolClass.objects.filter(school=school, name__iexact=name, section__iexact=section).exists():
            errors["non_field_errors"] = [f"Class {name}-{section} already exists in this school."]

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        school_class = SchoolClass.objects.create(
            school=school,
            name=name,
            section=section,
            class_teacher=class_teacher,
        )
        return Response(ClassSerializer(school_class).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsPrincipalOrSuperuser])
@throttle_classes([AdminWriteThrottle])
def admin_class_detail(request, pk):
    u = request.user
    if u.is_superuser:
        school_class = get_object_or_404(SchoolClass.objects.select_related("school", "class_teacher"), pk=pk)
    else:
        school = get_principal_school(u)
        school_class = get_object_or_404(SchoolClass.objects.select_related("school", "class_teacher"), pk=pk, school=school)

    if request.method == "GET":
        return Response(ClassSerializer(school_class).data)

    elif request.method == "PATCH":
        data = request.data
        name = clean_value(data.get("name", school_class.name))
        section = clean_value(data.get("section", school_class.section))
        teacher_id = data.get("classTeacher", "NOT_PROVIDED")

        errors = {}
        if not name:
            errors["name"] = ["Class name is required."]
        if not section:
            errors["section"] = ["Section is required."]

        if SchoolClass.objects.filter(school=school_class.school, name__iexact=name, section__iexact=section).exclude(id=school_class.id).exists():
            errors["non_field_errors"] = [f"Class {name}-{section} already exists."]

        if teacher_id != "NOT_PROVIDED":
            if teacher_id:
                try:
                    school_class.class_teacher = Teacher.objects.get(id=teacher_id, school=school_class.school)
                except Teacher.DoesNotExist:
                    errors["classTeacher"] = ["Teacher not found or not in this school."]
            else:
                school_class.class_teacher = None

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        school_class.name = name
        school_class.section = section
        school_class.save()
        return Response(ClassSerializer(school_class).data)

    elif request.method == "DELETE":
        school_class.delete()
        return Response({"detail": "Class deleted successfully"}, status=status.HTTP_200_OK)


# ==============================================================================
# 2. TEACHERS CRUD
# ==============================================================================

@api_view(["GET", "POST"])
@permission_classes([IsPrincipalOrSuperuser])
@throttle_classes([AdminWriteThrottle])
def admin_teachers(request):
    u = request.user
    if request.method == "GET":
        qs = Teacher.objects.select_related("user", "school")
        if not u.is_superuser:
            school = get_principal_school(u)
            qs = qs.filter(school=school)
        else:
            school_filter = request.query_params.get("school")
            if school_filter:
                qs = qs.filter(school_id=school_filter)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                user__first_name__icontains=search
            ) | qs.filter(
                user__last_name__icontains=search
            ) | qs.filter(
                employee_id__icontains=search
            ) | qs.filter(
                designation__icontains=search
            )

        qs = qs.order_by("-id")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = TeacherSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    elif request.method == "POST":
        data = request.data
        first_name = clean_value(data.get("firstName") or data.get("first_name"))
        last_name = clean_value(data.get("lastName") or data.get("last_name"))
        username = clean_value(data.get("username"))
        email = clean_value(data.get("email"))
        mobile = clean_value(data.get("mobile"))
        password = data.get("password") or ""
        employee_id = clean_value(data.get("employeeId") or data.get("employee_id"))
        designation = clean_value(data.get("designation")) or "Teacher"
        qualification = clean_value(data.get("qualification"))
        joining_date = convert_date(data.get("joiningDate") or data.get("joining_date"))

        errors = {}
        if not first_name:
            errors["firstName"] = ["First name is required."]
        if not username:
            errors["username"] = ["Username is required."]
        elif User.objects.filter(username__iexact=username).exists():
            errors["username"] = ["A user with this username already exists."]

        if not employee_id:
            errors["employeeId"] = ["Employee ID is required."]
        elif Teacher.objects.filter(employee_id__iexact=employee_id).exists():
            errors["employeeId"] = ["A teacher with this employee ID already exists."]

        if not password:
            errors["password"] = ["Password is required."]
        else:
            try:
                validate_password(password)
            except ValidationError as e:
                errors["password"] = list(e.messages)

        if email and User.objects.filter(email__iexact=email).exists():
            errors["email"] = ["Email already in use."]

        school = get_target_school(request)

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                email=email,
                mobile=mobile,
                role="teacher",
            )
            teacher = Teacher.objects.create(
                user=user,
                school=school,
                employee_id=employee_id,
                designation=designation,
                qualification=qualification,
                joining_date=joining_date,
            )

        resp_data = TeacherSerializer(teacher).data
        resp_data["generatedCredentials"] = {
            "username": username,
            "password": password,
        }
        return Response(resp_data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsPrincipalOrSuperuser])
@throttle_classes([AdminWriteThrottle])
def admin_teacher_detail(request, pk):
    u = request.user
    if u.is_superuser:
        teacher = get_object_or_404(Teacher.objects.select_related("user", "school"), pk=pk)
    else:
        school = get_principal_school(u)
        teacher = get_object_or_404(Teacher.objects.select_related("user", "school"), pk=pk, school=school)

    if request.method == "GET":
        return Response(TeacherSerializer(teacher).data)

    elif request.method == "PATCH":
        data = request.data
        user = teacher.user
        errors = {}

        if "firstName" in data or "first_name" in data:
            user.first_name = clean_value(data.get("firstName") or data.get("first_name"))
        if "lastName" in data or "last_name" in data:
            user.last_name = clean_value(data.get("lastName") or data.get("last_name"))
        if "email" in data:
            new_email = clean_value(data.get("email"))
            if new_email and User.objects.filter(email__iexact=new_email).exclude(id=user.id).exists():
                errors["email"] = ["Email already in use."]
            else:
                user.email = new_email
        if "mobile" in data:
            user.mobile = clean_value(data.get("mobile"))

        if "designation" in data:
            teacher.designation = clean_value(data.get("designation"))
        if "qualification" in data:
            teacher.qualification = clean_value(data.get("qualification"))
        if "joiningDate" in data or "joining_date" in data:
            teacher.joining_date = convert_date(data.get("joiningDate") or data.get("joining_date"))

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user.save()
            teacher.save()

        return Response(TeacherSerializer(teacher).data)

    elif request.method == "DELETE":
        with transaction.atomic():
            user = teacher.user
            teacher.delete()
            user.delete()
        return Response({"detail": "Teacher deleted successfully"}, status=status.HTTP_200_OK)


# ==============================================================================
# 3. STUDENTS CRUD
# ==============================================================================

@api_view(["GET", "POST"])
@permission_classes([IsPrincipalOrSuperuser])
@throttle_classes([AdminWriteThrottle])
def admin_students(request):
    u = request.user
    if request.method == "GET":
        qs = Student.objects.select_related("user", "school", "class_section")
        if not u.is_superuser:
            school = get_principal_school(u)
            qs = qs.filter(school=school)
        else:
            school_filter = request.query_params.get("school")
            if school_filter:
                qs = qs.filter(school_id=school_filter)

        class_id = request.query_params.get("class")
        if class_id:
            qs = qs.filter(class_section_id=class_id)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                user__first_name__icontains=search
            ) | qs.filter(
                user__last_name__icontains=search
            ) | qs.filter(
                admission_number__icontains=search
            )

        qs = qs.order_by("-id")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = StudentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    elif request.method == "POST":
        data = request.data
        first_name = clean_value(data.get("firstName") or data.get("first_name"))
        last_name = clean_value(data.get("lastName") or data.get("last_name"))
        username = clean_value(data.get("username"))
        email = clean_value(data.get("email"))
        mobile = clean_value(data.get("mobile"))
        password = data.get("password") or ""
        admission_number = clean_value(data.get("admissionNumber") or data.get("admission_number"))
        class_section_id = data.get("classSection") or data.get("class_section")
        gender = clean_value(data.get("gender"))
        date_of_birth = convert_date(data.get("dateOfBirth") or data.get("date_of_birth"))
        address = clean_value(data.get("address"))

        school = get_target_school(request)
        errors = {}

        if not first_name:
            errors["firstName"] = ["First name is required."]
        if not username:
            errors["username"] = ["Username is required."]
        elif User.objects.filter(username__iexact=username).exists():
            errors["username"] = ["A user with this username already exists."]

        if not admission_number:
            errors["admissionNumber"] = ["Admission number is required."]
        elif Student.objects.filter(admission_number__iexact=admission_number).exists():
            errors["admissionNumber"] = ["A student with this admission number already exists."]

        if not password:
            errors["password"] = ["Password is required."]
        else:
            try:
                validate_password(password)
            except ValidationError as e:
                errors["password"] = list(e.messages)

        class_section = None
        if class_section_id:
            try:
                class_section = SchoolClass.objects.get(id=class_section_id, school=school)
            except SchoolClass.DoesNotExist:
                errors["classSection"] = ["Class section does not belong to this institute."]

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                email=email,
                mobile=mobile,
                role="student",
            )
            student = Student.objects.create(
                user=user,
                school=school,
                class_section=class_section,
                admission_number=admission_number,
                gender=gender,
                date_of_birth=date_of_birth,
                address=address,
            )

        resp_data = StudentSerializer(student).data
        resp_data["generatedCredentials"] = {
            "username": username,
            "password": password,
        }
        return Response(resp_data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsPrincipalOrSuperuser])
@throttle_classes([AdminWriteThrottle])
def admin_student_detail(request, pk):
    u = request.user
    if u.is_superuser:
        student = get_object_or_404(Student.objects.select_related("user", "school", "class_section"), pk=pk)
    else:
        school = get_principal_school(u)
        student = get_object_or_404(Student.objects.select_related("user", "school", "class_section"), pk=pk, school=school)

    if request.method == "GET":
        return Response(StudentSerializer(student).data)

    elif request.method == "PATCH":
        data = request.data
        user = student.user
        errors = {}

        if "firstName" in data or "first_name" in data:
            user.first_name = clean_value(data.get("firstName") or data.get("first_name"))
        if "lastName" in data or "last_name" in data:
            user.last_name = clean_value(data.get("lastName") or data.get("last_name"))
        if "email" in data:
            new_email = clean_value(data.get("email"))
            if new_email and User.objects.filter(email__iexact=new_email).exclude(id=user.id).exists():
                errors["email"] = ["Email already in use."]
            else:
                user.email = new_email
        if "mobile" in data:
            user.mobile = clean_value(data.get("mobile"))

        if "classSection" in data or "class_section" in data:
            sec_id = data.get("classSection") or data.get("class_section")
            if sec_id:
                try:
                    student.class_section = SchoolClass.objects.get(id=sec_id, school=student.school)
                except SchoolClass.DoesNotExist:
                    errors["classSection"] = ["Class section not found or not in this school."]
            else:
                student.class_section = None

        if "gender" in data:
            student.gender = clean_value(data.get("gender"))
        if "dateOfBirth" in data or "date_of_birth" in data:
            student.date_of_birth = convert_date(data.get("dateOfBirth") or data.get("date_of_birth"))
        if "address" in data:
            student.address = clean_value(data.get("address"))

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user.save()
            student.save()

        return Response(StudentSerializer(student).data)

    elif request.method == "DELETE":
        with transaction.atomic():
            user = student.user
            student.delete()
            user.delete()
        return Response({"detail": "Student deleted successfully"}, status=status.HTTP_200_OK)


# ==============================================================================
# 4. SUPERUSER ONLY: SCHOOLS & PRINCIPALS CRUD
# ==============================================================================

@api_view(["GET", "POST"])
@permission_classes([IsSuperuserOnly])
@throttle_classes([AdminWriteThrottle])
def admin_schools_manage(request):
    if request.method == "GET":
        qs = School.objects.select_related("principal").order_by("name")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(code__icontains=search)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(SchoolSerializer(page, many=True).data)

    elif request.method == "POST":
        data = request.data
        name = clean_value(data.get("name"))
        code = clean_value(data.get("code"))
        address = clean_value(data.get("address"))
        city = clean_value(data.get("city")) or "Indore"
        phone = clean_value(data.get("phone"))
        email = clean_value(data.get("email"))

        errors = {}
        if not name:
            errors["name"] = ["School name is required."]
        if not code:
            errors["code"] = ["School code is required."]
        elif School.objects.filter(code__iexact=code).exists():
            errors["code"] = ["School code must be unique."]

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        school = School.objects.create(
            name=name,
            code=code,
            address=address,
            city=city,
            phone=phone,
            email=email,
        )
        return Response(SchoolSerializer(school).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsSuperuserOnly])
@throttle_classes([AdminWriteThrottle])
def admin_school_detail_manage(request, pk):
    school = get_object_or_404(School.objects.select_related("principal"), pk=pk)

    if request.method == "GET":
        return Response(SchoolSerializer(school).data)

    elif request.method == "PATCH":
        data = request.data
        if "name" in data:
            school.name = clean_value(data.get("name"))
        if "address" in data:
            school.address = clean_value(data.get("address"))
        if "city" in data:
            school.city = clean_value(data.get("city"))
        if "phone" in data:
            school.phone = clean_value(data.get("phone"))
        if "email" in data:
            school.email = clean_value(data.get("email"))

        school.save()
        return Response(SchoolSerializer(school).data)

    elif request.method == "DELETE":
        school.delete()
        return Response({"detail": "School deleted successfully"}, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
@permission_classes([IsSuperuserOnly])
@throttle_classes([AdminWriteThrottle])
def admin_principals_manage(request):
    if request.method == "GET":
        qs = User.objects.filter(role="principal").select_related("principal_school").order_by("-id")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(username__icontains=search) | qs.filter(first_name__icontains=search)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(PrincipalSerializer(page, many=True).data)

    elif request.method == "POST":
        data = request.data
        first_name = clean_value(data.get("firstName") or data.get("first_name"))
        last_name = clean_value(data.get("lastName") or data.get("last_name"))
        username = clean_value(data.get("username"))
        email = clean_value(data.get("email"))
        mobile = clean_value(data.get("mobile"))
        password = data.get("password") or ""
        school_id = data.get("schoolId") or data.get("school")

        errors = {}
        if not username:
            errors["username"] = ["Username is required."]
        elif User.objects.filter(username__iexact=username).exists():
            errors["username"] = ["Username already taken."]

        if not password:
            errors["password"] = ["Password is required."]
        else:
            try:
                validate_password(password)
            except ValidationError as e:
                errors["password"] = list(e.messages)

        school = None
        if not school_id:
            errors["schoolId"] = ["A school must be selected for the principal."]
        else:
            try:
                school = School.objects.get(id=school_id)
            except School.DoesNotExist:
                errors["schoolId"] = ["Selected school does not exist."]

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                email=email,
                mobile=mobile,
                role="principal",
            )
            school.principal = user
            school.save()

        resp_data = PrincipalSerializer(user).data
        resp_data["generatedCredentials"] = {
            "username": username,
            "password": password,
        }
        return Response(resp_data, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsSuperuserOnly])
@throttle_classes([AdminWriteThrottle])
def admin_principal_detail_manage(request, pk):
    principal = get_object_or_404(User, pk=pk, role="principal")
    with transaction.atomic():
        School.objects.filter(principal=principal).update(principal=None)
        principal.delete()
    return Response({"detail": "Principal deleted successfully"}, status=status.HTTP_200_OK)


# ==============================================================================
# 5. EXCEL IMPORT (PREVIEW & CONFIRM)
# ==============================================================================

MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_IMPORT_ROWS = 5000


@api_view(["POST"])
@permission_classes([IsPrincipalOrSuperuser])
@throttle_classes([ImportUploadThrottle])
def admin_import_preview(request):
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return Response({"file": ["Please select a CSV or Excel file to upload."]}, status=status.HTTP_400_BAD_REQUEST)

    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in [".csv", ".xlsx", ".xls"]:
        return Response({"file": ["Only .csv, .xlsx, or .xls files are supported."]}, status=status.HTTP_400_BAD_REQUEST)

    if uploaded_file.size > MAX_IMPORT_FILE_SIZE:
        return Response({"file": ["File size exceeds maximum allowed limit of 5 MB."]}, status=status.HTTP_400_BAD_REQUEST)

    target_school = get_target_school(request)

    try:
        df = read_uploaded_file(uploaded_file)
    except Exception as e:
        return Response({"file": [f"Could not parse spreadsheet: {str(e)}"]}, status=status.HTTP_400_BAD_REQUEST)

    total_rows = len(df)
    if total_rows > MAX_IMPORT_ROWS:
        return Response(
            {"file": [f"Spreadsheet contains {total_rows} rows, exceeding the 5,000 maximum row limit."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate essential columns
    if "student_id" not in df.columns or "student_name" not in df.columns:
        return Response(
            {"file": ["Spreadsheet must contain 'Student ID' and 'Student Name' columns."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Save to temp file securely
    import_folder = os.path.join(settings.MEDIA_ROOT, "import_temp")
    os.makedirs(import_folder, exist_ok=True)
    temp_filename = f"{uuid.uuid4().hex}_{os.path.basename(uploaded_file.name)}"
    temp_path = os.path.join(import_folder, temp_filename)

    uploaded_file.seek(0)
    with open(temp_path, "wb") as dest:
        for chunk in uploaded_file.chunks():
            dest.write(chunk)

    token = signing.dumps({
        "file": temp_path,
        "school_id": target_school.id,
        "filename": uploaded_file.name,
    })

    # Prepare preview rows (first 50) and evaluate per-row validation
    columns = list(df.columns)
    preview_rows = []
    has_errors = False

    existing_admissions = set(Student.objects.filter(school=target_school).values_list("admission_number", flat=True))

    for idx, row in df.head(50).iterrows():
        row_num = idx + 2
        adm_no = clean_value(row.get("student_id", ""))
        name = clean_value(row.get("student_name", ""))
        row_errors = []

        if not adm_no:
            row_errors.append("Missing Student ID")
        elif adm_no in existing_admissions:
            row_errors.append(f"Duplicate Admission No ({adm_no})")

        if not name:
            row_errors.append("Missing Student Name")

        if row_errors:
            has_errors = True

        preview_rows.append({
            "row": row_num,
            "studentId": adm_no,
            "studentName": name,
            "class": clean_value(row.get("class", "")),
            "section": clean_value(row.get("section", "")),
            "email": clean_value(row.get("email", "")),
            "mobile": clean_value(row.get("mobile_no", "")),
            "errors": row_errors,
        })

    return Response({
        "importToken": token,
        "filename": uploaded_file.name,
        "totalRows": total_rows,
        "previewCount": len(preview_rows),
        "columns": columns,
        "preview": preview_rows,
        "hasErrors": has_errors,
        "targetSchool": {
            "id": target_school.id,
            "name": target_school.name,
            "code": target_school.code,
        },
    })


@api_view(["POST"])
@permission_classes([IsPrincipalOrSuperuser])
@throttle_classes([AdminWriteThrottle])
def admin_import_confirm(request):
    token = request.data.get("importToken") or request.data.get("import_token")
    if not token:
        return Response({"importToken": ["Import token is missing."]}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token_data = signing.loads(token, max_age=3600)
    except signing.BadSignature:
        return Response({"importToken": ["Import request is invalid or has expired."]}, status=status.HTTP_400_BAD_REQUEST)

    temp_path = token_data.get("file")
    school_id = token_data.get("school_id")
    filename = token_data.get("filename", "import.xlsx")

    u = request.user
    if not u.is_superuser:
        school = get_principal_school(u)
        if school.id != school_id:
            raise PermissionDenied("Cannot confirm import for another school.")
    else:
        school = get_object_or_404(School, id=school_id)

    if not temp_path or not os.path.exists(temp_path):
        return Response({"detail": "Temporary import file not found on server."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with open(temp_path, "rb") as f:
            class WrappedFile:
                def __init__(self, f_obj, name):
                    self.f_obj = f_obj
                    self.name = name
                def read(self, *args, **kwargs):
                    return self.f_obj.read(*args, **kwargs)
                def seek(self, *args, **kwargs):
                    return self.f_obj.seek(*args, **kwargs)

            df = read_uploaded_file(WrappedFile(f, filename))
    except Exception as e:
        return Response({"detail": f"Error reading temporary file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
    finally:
        # Securely delete temporary file after parsing
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    total = len(df)
    imported = 0
    duplicate = 0
    errors = []

    with transaction.atomic():
        for idx, row in df.iterrows():
            row_num = idx + 2
            admission_no = clean_value(row.get("student_id", ""))
            student_name = clean_value(row.get("student_name", ""))

            if not admission_no or not student_name:
                errors.append(f"Row {row_num}: Student ID or Name is blank.")
                continue

            if Student.objects.filter(admission_number=admission_no).exists():
                duplicate += 1
                continue

            first_name, last_name = split_name(student_name)
            base_username = f"{school.code.lower()}_{admission_no.lower()}"
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}_{counter}"
                counter += 1

            user = User.objects.create_user(
                username=username,
                password="Student@123",
                first_name=first_name,
                last_name=last_name,
                email=clean_value(row.get("email", "")),
                role="student",
            )

            class_name = clean_value(row.get("class", ""))
            section = clean_value(row.get("section", ""))
            school_class = None
            if class_name:
                school_class, _ = SchoolClass.objects.get_or_create(
                    school=school,
                    name=class_name,
                    section=section,
                )

            Student.objects.create(
                user=user,
                school=school,
                class_section=school_class,
                admission_number=admission_no,
                date_of_birth=convert_date(row.get("date_of_birth", "")),
                gender=clean_value(row.get("gender", "")),
                address=clean_value(row.get("address", "")),
            )
            imported += 1

    return Response({
        "total": total,
        "imported": imported,
        "duplicate": duplicate,
        "errorCount": len(errors),
        "errors": errors[:50],
        "defaultPassword": "Student@123",
    }, status=status.HTTP_200_OK)
