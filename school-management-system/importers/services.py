import io
import re
from django.core.exceptions import ValidationError
from django.db import transaction
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from academics.models import SchoolClass, Student, Teacher
from accounts.models import User
from audit.services import log_action
from credentials.models import UserSecurity
from credentials.services import generate_random_password, generate_username
from guardians.models import Guardian, StudentGuardian
from guardians.services import normalize_mobile

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_ROW_COUNT = 2000


def sanitize_cell_value(val):
    """
    Sanitizes values against CSV/Excel Formula Injection.
    If a value begins with =, +, -, @, \\t, or \\r, escapes it with a leading apostrophe.
    """
    if val is None:
        return ""
    val_str = str(val).strip()
    if val_str and val_str[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + val_str
    return val_str


def clean_cell_string(val):
    """
    Returns stripped string with formula injection escaping.
    """
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        val = int(val)
    return sanitize_cell_value(val).strip()


def normalize_class_name(val):
    """
    Normalizes class/standard for comparison:
    - Treats numeric cell 10 and '10' the same.
    - Strips whitespace.
    - Strips formula injection apostrophe if present.
    - Case-insensitive.
    - Removes leading 'class', 'std', 'std.', 'standard' word.
    """
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        val = int(val)
    s = str(val).strip()
    if s.startswith("'"):
        s = s[1:].strip()
    norm = re.sub(r'^(?:class|std\.?|standard)\s*[-:]?\s*', '', s, flags=re.IGNORECASE).strip()
    return norm.lower() if norm else s.lower()


def normalize_section_name(val):
    """
    Normalizes section:
    - Strips whitespace.
    - Uppercase.
    """
    if val is None:
        return ""
    s = str(val).strip()
    if s.startswith("'"):
        s = s[1:].strip()
    return s.upper()


def make_internal_id(school_code, raw_id):
    """
    Stores admission_number and employee_id internally as '<schoolcode>-<value>'.
    Idempotent if already prefixed.
    """
    clean_code = str(school_code or "").strip().upper()
    clean_raw = str(raw_id or "").strip()
    prefix = f"{clean_code}-"
    if clean_raw.upper().startswith(prefix):
        return clean_raw
    return f"{prefix}{clean_raw}"


def format_display_id(school_code, internal_id):
    """
    Displays admission_number and employee_id without '<schoolcode>-' prefix.
    """
    clean_code = str(school_code or "").strip().upper()
    clean_id = str(internal_id or "").strip()
    prefix = f"{clean_code}-"
    if clean_id.upper().startswith(prefix):
        return clean_id[len(prefix):]
    return clean_id


def generate_teacher_template():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Teachers"

    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    sample_font = Font(name="Arial", size=10, italic=True, color="6B7280")
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")

    headers = [
        "Employee ID*",
        "First Name*",
        "Last Name*",
        "Email",
        "Mobile*",
        "Designation",
        "Department",
    ]

    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    # Sample row for guidance
    sample_row = [
        "EMP001",
        "Ramesh",
        "Sharma",
        "ramesh.sharma@example.com",
        "9876543210",
        "Senior Teacher",
        "Mathematics",
    ]
    for col_idx, val in enumerate(sample_row, start=1):
        cell = ws.cell(row=2, column=col_idx, value=val)
        cell.font = sample_font
        cell.alignment = left_align

    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = 22

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def generate_student_template():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Students"

    header_fill = PatternFill(start_color="047857", end_color="047857", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    sample_font = Font(name="Arial", size=10, italic=True, color="6B7280")
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")

    headers = [
        "Admission Number*",
        "First Name*",
        "Last Name*",
        "Class*",
        "Section*",
        "Guardian Name*",
        "Guardian Mobile*",
        "Guardian Relation*",
    ]

    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    sample_row = [
        "ADM1001",
        "Aarav",
        "Patel",
        "10",
        "A",
        "Suresh Patel",
        "9876543210",
        "father",
    ]
    for col_idx, val in enumerate(sample_row, start=1):
        cell = ws.cell(row=2, column=col_idx, value=val)
        cell.font = sample_font
        cell.alignment = left_align

    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = 22

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def validate_teacher_import(file_obj, school):
    """
    Dry-run validation for teacher excel sheet.
    Returns: (valid_rows, errors, total_rows)
    """
    if file_obj.size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(f"File size exceeds maximum allowed limit of 5 MB ({MAX_FILE_SIZE_BYTES} bytes).")

    wb = openpyxl.load_workbook(file_obj, data_only=False)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValidationError("Excel sheet is empty.")

    header_row = [str(c or "").strip().lower() for c in rows[0]]
    field_map = {}
    for idx, col_name in enumerate(header_row):
        if "employee" in col_name or "emp" in col_name:
            field_map["employee_id"] = idx
        elif "first" in col_name:
            field_map["first_name"] = idx
        elif "last" in col_name:
            field_map["last_name"] = idx
        elif "email" in col_name:
            field_map["email"] = idx
        elif "mobile" in col_name or "phone" in col_name:
            field_map["mobile"] = idx
        elif "designation" in col_name:
            field_map["designation"] = idx
        elif "dept" in col_name or "department" in col_name:
            field_map["department"] = idx

    required_keys = ["employee_id", "first_name", "last_name", "mobile"]
    missing = [k for k in required_keys if k not in field_map]
    if missing:
        raise ValidationError(f"Missing required columns in header: {', '.join(missing)}")

    data_rows = rows[1:]
    if len(data_rows) > MAX_ROW_COUNT:
        raise ValidationError(f"File contains {len(data_rows)} rows. Maximum allowed is {MAX_ROW_COUNT} rows.")

    valid_rows = []
    errors = []
    seen_in_file_ids = set()

    for row_idx, row in enumerate(data_rows, start=2):
        # Skip completely empty rows
        if not any(row):
            continue

        emp_id = clean_cell_string(row[field_map["employee_id"]])
        first_name = clean_cell_string(row[field_map["first_name"]])
        last_name = clean_cell_string(row[field_map["last_name"]])
        raw_mobile = str(row[field_map["mobile"]] or "").strip()
        email = clean_cell_string(row[field_map["email"]]) if "email" in field_map and field_map["email"] < len(row) else ""
        designation = clean_cell_string(row[field_map["designation"]]) if "designation" in field_map and field_map["designation"] < len(row) else "Teacher"
        department = clean_cell_string(row[field_map["department"]]) if "department" in field_map and field_map["department"] < len(row) else ""

        row_errors = []

        if not emp_id:
            row_errors.append("Employee ID is required.")
        if not first_name:
            row_errors.append("First name is required.")
        if not last_name:
            row_errors.append("Last name is required.")

        norm_mobile = normalize_mobile(raw_mobile)
        if len(norm_mobile) != 10:
            row_errors.append(f"Invalid mobile number '{raw_mobile}'. Must be a 10-digit number.")

        if email and "@" not in email:
            row_errors.append(f"Invalid email address '{email}'.")

        if emp_id:
            clean_eid = emp_id.strip().upper()
            if clean_eid in seen_in_file_ids:
                row_errors.append(f"Duplicate Employee ID '{emp_id}' within this sheet.")
            seen_in_file_ids.add(clean_eid)

            internal_eid = make_internal_id(school.code, emp_id)
            other_school_teacher = Teacher.objects.filter(employee_id=internal_eid).exclude(school=school).first()
            if other_school_teacher:
                row_errors.append(f"Employee ID '{emp_id}' is already registered at another school.")

        if row_errors:
            errors.append({"row": row_idx, "employee_id": emp_id, "errors": row_errors})
        else:
            valid_rows.append({
                "row_num": row_idx,
                "employee_id": emp_id,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "mobile": norm_mobile,
                "designation": designation or "Teacher",
                "department": department,
            })

    return valid_rows, errors, len(data_rows)


def validate_student_import(file_obj, school):
    """
    Dry-run validation for student excel sheet.
    Returns: (valid_rows, errors, total_rows)
    """
    if file_obj.size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(f"File size exceeds maximum allowed limit of 5 MB ({MAX_FILE_SIZE_BYTES} bytes).")

    wb = openpyxl.load_workbook(file_obj, data_only=False)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValidationError("Excel sheet is empty.")

    header_row = [str(c or "").strip().lower() for c in rows[0]]
    field_map = {}
    for idx, col_name in enumerate(header_row):
        if "admission" in col_name or "adm" in col_name:
            field_map["admission_number"] = idx
        elif "first" in col_name:
            field_map["first_name"] = idx
        elif "last" in col_name:
            field_map["last_name"] = idx
        elif col_name == "class" or "class" in col_name:
            field_map["class"] = idx
        elif "section" in col_name:
            field_map["section"] = idx
        elif "guardian" in col_name and ("name" in col_name or "parent" in col_name):
            field_map["guardian_name"] = idx
        elif "guardian" in col_name and ("mobile" in col_name or "phone" in col_name):
            field_map["guardian_mobile"] = idx
        elif "relation" in col_name:
            field_map["guardian_relation"] = idx

    required_keys = ["admission_number", "first_name", "last_name", "class", "section", "guardian_name", "guardian_mobile"]
    missing = [k for k in required_keys if k not in field_map]
    if missing:
        raise ValidationError(f"Missing required columns in header: {', '.join(missing)}")

    data_rows = rows[1:]
    if len(data_rows) > MAX_ROW_COUNT:
        raise ValidationError(f"File contains {len(data_rows)} rows. Maximum allowed is {MAX_ROW_COUNT} rows.")

    valid_rows = []
    errors = []
    seen_in_file_adm_nos = set()

    # Pre-fetch and index all classes in this school for fast, normalized lookup
    school_classes = list(SchoolClass.objects.filter(school=school))
    class_map = {}
    for c in school_classes:
        norm_c_name = normalize_class_name(c.name)
        norm_c_sec = normalize_section_name(c.section)
        # Store exact lowercase name key
        class_map[(str(c.name).strip().lower(), norm_c_sec)] = c
        # Store normalized name key
        if (norm_c_name, norm_c_sec) not in class_map:
            class_map[(norm_c_name, norm_c_sec)] = c

    # Available classes formatted for error message: "10-A, 10-B, ..."
    sorted_classes = sorted(school_classes, key=lambda c: (str(c.name), str(c.section)))
    available_classes_str = (
        ", ".join(f"{c.name}-{c.section}" for c in sorted_classes)
        if sorted_classes
        else "None"
    )

    for row_idx, row in enumerate(data_rows, start=2):
        if not any(row):
            continue

        adm_no = clean_cell_string(row[field_map["admission_number"]])
        first_name = clean_cell_string(row[field_map["first_name"]])
        last_name = clean_cell_string(row[field_map["last_name"]])
        raw_class = row[field_map["class"]]
        raw_section = row[field_map["section"]]
        class_name = clean_cell_string(raw_class)
        section_name = normalize_section_name(raw_section)
        guardian_name = clean_cell_string(row[field_map["guardian_name"]])
        raw_guardian_mobile = str(row[field_map["guardian_mobile"]] or "").strip()
        guardian_rel = (
            clean_cell_string(row[field_map["guardian_relation"]]).lower()
            if "guardian_relation" in field_map and field_map["guardian_relation"] < len(row)
            else "guardian"
        )
        if guardian_rel not in ("father", "mother", "guardian", "other"):
            guardian_rel = "guardian"

        row_errors = []

        if not adm_no:
            row_errors.append("Admission number is required.")
        if not first_name:
            row_errors.append("First name is required.")
        if not last_name:
            row_errors.append("Last name is required.")
        if not class_name:
            row_errors.append("Class is required.")
        if not section_name:
            row_errors.append("Section is required.")
        if not guardian_name:
            row_errors.append("Guardian name is required.")

        norm_guardian_mobile = normalize_mobile(raw_guardian_mobile)
        if len(norm_guardian_mobile) != 10:
            row_errors.append(f"Invalid guardian mobile '{raw_guardian_mobile}'. Must be a 10-digit number.")
        else:
            existing_parent_user = User.objects.filter(username=norm_guardian_mobile).first()
            if existing_parent_user:
                sec = getattr(existing_parent_user, "security", None)
                is_import_user = bool(sec and sec.created_via == "import")
                is_approved_guardian = Guardian.objects.filter(user=existing_parent_user, link_status="approved").exists()

                if not (is_import_user or is_approved_guardian):
                    row_errors.append(f"Mobile '{norm_guardian_mobile}' is already registered by another account.")

        # Verify class exists in school using normalized lookup
        class_obj = None
        if class_name and section_name:
            norm_cls = normalize_class_name(raw_class)
            # Try exact first, then normalized class name
            class_obj = class_map.get((class_name.lower(), section_name))
            if not class_obj:
                class_obj = class_map.get((norm_cls, section_name))

            if not class_obj:
                row_errors.append(
                    f"Class '{class_name} {section_name}' does not exist in your school. Available: {available_classes_str}."
                )

        if adm_no:
            clean_adm = adm_no.strip().upper()
            if clean_adm in seen_in_file_adm_nos:
                row_errors.append(f"Duplicate Admission Number '{adm_no}' within this sheet.")
            seen_in_file_adm_nos.add(clean_adm)

            internal_adm = make_internal_id(school.code, adm_no)
            other_school_student = Student.objects.filter(admission_number=internal_adm).exclude(school=school).first()
            if other_school_student:
                row_errors.append(f"Admission number '{adm_no}' is already registered at another school.")

        if row_errors:
            errors.append({"row": row_idx, "admission_number": adm_no, "errors": row_errors})
        else:
            valid_rows.append({
                "row_num": row_idx,
                "admission_number": adm_no,
                "first_name": first_name,
                "last_name": last_name,
                "class_name": class_obj.name,
                "section_name": class_obj.section,
                "class_id": class_obj.id,
                "guardian_name": guardian_name,
                "guardian_mobile": norm_guardian_mobile,
                "guardian_relation": guardian_rel,
            })

    return valid_rows, errors, len(data_rows)


def commit_teacher_import(valid_rows, actor, school, request=None):
    """
    Executes teacher import inside an atomic transaction.
    Idempotent: updates existing teacher if employee_id already exists in school.
    Returns: list of credentials rows for the sheet builder.
    """
    credentials_rows = []

    with transaction.atomic():
        for item in valid_rows:
            emp_id = item["employee_id"]
            first_name = item["first_name"]
            last_name = item["last_name"]
            email = item["email"]
            mobile = item["mobile"]
            designation = item["designation"]
            department = item["department"]

            internal_eid = make_internal_id(school.code, emp_id)

            existing_teacher = Teacher.objects.select_related("user").filter(
                school=school,
                employee_id=internal_eid,
            ).first()

            if existing_teacher:
                # Idempotent update
                u = existing_teacher.user
                u.first_name = first_name
                u.last_name = last_name
                if email:
                    u.email = email
                u.mobile = mobile
                u.save()

                existing_teacher.designation = designation
                if department:
                    existing_teacher.qualification = department
                existing_teacher.save()
            else:
                # New teacher
                username = generate_username(school.code, "T", emp_id)
                temp_password = generate_random_password(12)

                user = User.objects.create_user(
                    username=username,
                    email=email or f"{username.lower()}@indoreedu.local",
                    mobile=mobile,
                    password=temp_password,
                    first_name=first_name,
                    last_name=last_name,
                    role="teacher",
                )

                teacher = Teacher.objects.create(
                    user=user,
                    school=school,
                    employee_id=internal_eid,
                    designation=designation,
                    qualification=department,
                )

                UserSecurity.objects.create(
                    user=user,
                    must_change_password=True,
                    created_via="import",
                )

                credentials_rows.append({
                    "role": "Teacher",
                    "name": f"{first_name} {last_name}",
                    "identifier": format_display_id(school.code, internal_eid),
                    "username": username,
                    "password": temp_password,
                    "notes": "Must change password on first login",
                })

        log_action(
            actor=actor,
            school=school,
            action="import.teachers",
            changes={"imported_count": len(valid_rows), "new_users": len(credentials_rows)},
            request=request,
        )

    return credentials_rows


def commit_student_import(valid_rows, actor, school, request=None):
    """
    Executes student import with guardian deduplication and linking.
    Idempotent: updates existing student if admission_number exists in school.
    Returns: list of credentials rows for students and newly created parents.
    """
    credentials_rows = []
    seen_parent_mobiles_in_credentials = set()

    with transaction.atomic():
        for item in valid_rows:
            adm_no = item["admission_number"]
            first_name = item["first_name"]
            last_name = item["last_name"]
            class_id = item["class_id"]
            guardian_name = item["guardian_name"]
            guardian_mobile = item["guardian_mobile"]
            guardian_rel = item["guardian_relation"]

            school_class = SchoolClass.objects.get(pk=class_id, school=school)
            internal_adm = make_internal_id(school.code, adm_no)

            existing_student = Student.objects.select_related("user").filter(
                school=school,
                admission_number=internal_adm,
            ).first()

            if existing_student:
                # Idempotent update
                u = existing_student.user
                u.first_name = first_name
                u.last_name = last_name
                u.save()

                existing_student.class_section = school_class
                existing_student.save()
                student = existing_student
            else:
                # New student: User.mobile stays blank as per Decision 4
                username = generate_username(school.code, "S", adm_no)
                temp_password = generate_random_password(12)

                user = User.objects.create_user(
                    username=username,
                    email=f"{username.lower()}@indoreedu.local",
                    mobile="",
                    password=temp_password,
                    first_name=first_name,
                    last_name=last_name,
                    role="student",
                )

                student = Student.objects.create(
                    user=user,
                    school=school,
                    class_section=school_class,
                    admission_number=internal_adm,
                )

                UserSecurity.objects.create(
                    user=user,
                    must_change_password=True,
                    created_via="import",
                )

                credentials_rows.append({
                    "role": "Student",
                    "name": f"{first_name} {last_name}",
                    "identifier": format_display_id(school.code, internal_adm),
                    "username": username,
                    "password": temp_password,
                    "notes": "Must change password on first login",
                })

            # Guardian handling: Deduplicate by (school, mobile)
            guardian = Guardian.objects.filter(
                school=school,
                mobile=guardian_mobile,
            ).first()

            if not guardian:
                guardian = Guardian.objects.create(
                    school=school,
                    full_name=guardian_name,
                    mobile=guardian_mobile,
                    link_status="approved",
                )
            else:
                if guardian.link_status != "approved":
                    guardian.link_status = "approved"
                    guardian.save()

            # Parent User handling: Lookup by username = 10-digit mobile (Decision 4)
            parent_user = User.objects.filter(username=guardian_mobile).first()
            if not parent_user:
                parent_temp_password = generate_random_password(12)
                parent_user = User.objects.create_user(
                    username=guardian_mobile,
                    email=f"parent.{guardian_mobile}@indoreedu.local",
                    mobile=guardian_mobile,
                    password=parent_temp_password,
                    first_name=guardian_name,
                    role="parent",
                )
                UserSecurity.objects.create(
                    user=parent_user,
                    must_change_password=True,
                    created_via="import",
                )
                if guardian_mobile not in seen_parent_mobiles_in_credentials:
                    seen_parent_mobiles_in_credentials.add(guardian_mobile)
                    credentials_rows.append({
                        "role": "Parent",
                        "name": guardian_name,
                        "identifier": guardian_mobile,
                        "username": guardian_mobile,
                        "password": parent_temp_password,
                        "notes": "Parent login via 10-digit mobile",
                    })
            else:
                # Existing parent user: NEVER reset or regenerate password (Requirement 4)
                if guardian_mobile not in seen_parent_mobiles_in_credentials:
                    seen_parent_mobiles_in_credentials.add(guardian_mobile)
                    credentials_rows.append({
                        "role": "Parent",
                        "name": parent_user.get_full_name() or guardian_name,
                        "identifier": guardian_mobile,
                        "username": guardian_mobile,
                        "password": "Existing account",
                        "notes": "Existing account",
                    })

            # Link Guardian to Parent User
            if guardian.user != parent_user:
                guardian.user = parent_user
                guardian.save()

            # Link Student to Guardian
            StudentGuardian.objects.get_or_create(
                student=student,
                guardian=guardian,
                defaults={
                    "relation": guardian_rel,
                    "is_primary": True,
                },
            )

        log_action(
            actor=actor,
            school=school,
            action="import.students",
            changes={"imported_count": len(valid_rows), "credentials_generated": len(credentials_rows)},
            request=request,
        )

    return credentials_rows
