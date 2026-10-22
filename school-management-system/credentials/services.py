import io
import re
import secrets
import string
from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from academics.models import SchoolClass, Student, Teacher
from accounts.models import User
from audit.services import log_action
from guardians.models import Guardian, StudentGuardian
from .models import UserSecurity


def format_display_id(school_code, internal_id):
    if not internal_id:
        return ""
    prefix = f"{school_code}-" if school_code else ""
    if prefix and str(internal_id).startswith(prefix):
        return str(internal_id)[len(prefix):]
    return str(internal_id)


def generate_password_for_mode(mode, role, display_id="", mobile="", school_code=""):
    """
    mode: 'random' (default) | 'id_pattern'
    id_pattern:
      student: "<AdmissionNo>@<last4 of guardian mobile>"
      teacher: "<EmployeeID>@<last4 of mobile>" (if no mobile, fall back to random)
      parent: "<last4 of mobile>@<schoolcode>"
    Use the display ID without the school prefix.
    """
    mode = str(mode or "").strip().lower()
    clean_digits = "".join(filter(str.isdigit, str(mobile or "")))
    last4 = clean_digits[-4:] if len(clean_digits) >= 4 else ""

    if mode == "id_pattern":
        if role == "student":
            clean_id = str(display_id or "").strip()
            if clean_id and last4:
                return f"{clean_id}@{last4}"
        elif role == "teacher":
            clean_id = str(display_id or "").strip()
            if clean_id and last4:
                return f"{clean_id}@{last4}"
            return generate_random_password(12)
        elif role == "parent":
            clean_school = re.sub(r"[^A-Za-z0-9]", "", str(school_code or "").upper())
            if last4 and clean_school:
                return f"{last4}@{clean_school}"

    return generate_random_password(12)


def generate_username(school_code, role_code, identifier):
    """
    Generates a unique username in format: <SCHOOLCODE>-<ROLE>-<IDENTIFIER>
    Example: DPS09-T-EMP101 or DPS09-S-ADM2024
    """
    clean_school = re.sub(r"[^A-Za-z0-9]", "", str(school_code or "").upper()) or "SCH"
    clean_role = re.sub(r"[^A-Za-z0-9]", "", str(role_code or "").upper()) or "U"
    clean_id = re.sub(r"[^A-Za-z0-9]", "", str(identifier or "").upper()) or "1"

    base_username = f"{clean_school}-{clean_role}-{clean_id}"
    username = base_username
    counter = 1
    while User.objects.filter(username__iexact=username).exists():
        username = f"{base_username}-{counter}"
        counter += 1

    return username


def generate_random_password(length=12):
    """
    Generates a cryptographically strong random password meeting Django's
    built-in password validators (length >= 8, mixed case, digits, symbols).
    """
    if length < 10:
        length = 10

    upper = string.ascii_uppercase
    lower = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*"

    # Ensure at least two of each character set
    password_chars = [
        secrets.choice(upper),
        secrets.choice(upper),
        secrets.choice(lower),
        secrets.choice(lower),
        secrets.choice(digits),
        secrets.choice(digits),
        secrets.choice(symbols),
        secrets.choice(symbols),
    ]

    all_chars = upper + lower + digits + symbols
    for _ in range(length - len(password_chars)):
        password_chars.append(secrets.choice(all_chars))

    # Shuffle cryptographically
    shuffled = []
    while password_chars:
        idx = secrets.randbelow(len(password_chars))
        shuffled.append(password_chars.pop(idx))

    return "".join(shuffled)


def reset_password_for_user(actor, target_user, school, request=None):
    """
    Resets password for target_user, sets must_change_password=True,
    logs credentials.reset in AuditLog, and returns the temporary password.
    Plaintext password is never persisted or logged.
    """
    temp_password = generate_random_password(12)
    target_user.set_password(temp_password)
    target_user.save()

    sec, _ = UserSecurity.objects.get_or_create(user=target_user)
    sec.must_change_password = True
    sec.save()

    log_action(
        actor=actor,
        school=school,
        action="credentials.reset",
        obj=target_user,
        changes={"must_change_password": True},
        request=request,
    )

    return temp_password


def change_user_password(user, old_password, new_password, request=None):
    """
    Changes a user's password, validates that new password is not equal to old password,
    username, or ID, runs Django password validators, clears must_change_password, and updates session.
    """
    if not user.check_password(old_password):
        raise ValidationError({"oldPassword": "Old password is incorrect."})

    # Cannot be equal to old password
    if old_password and new_password == old_password:
        raise ValidationError({"newPassword": "New password cannot be the same as the old password."})

    # Cannot be equal to username
    if new_password.lower() == user.username.lower():
        raise ValidationError({"newPassword": "New password cannot be the same as your username."})

    # Cannot be equal to student admission number
    if hasattr(user, "student_profile") and user.student_profile:
        adm = user.student_profile.admission_number or ""
        code = user.student_profile.school.code if user.student_profile.school else ""
        prefix = f"{code}-"
        display_adm = adm[len(prefix):] if (code and adm.startswith(prefix)) else adm
        if new_password.lower() in (adm.lower(), display_adm.lower()):
            raise ValidationError({"newPassword": "New password cannot be your admission number."})

    # Cannot be equal to teacher employee ID
    if hasattr(user, "teacher_profile") and user.teacher_profile:
        emp = user.teacher_profile.employee_id or ""
        code = user.teacher_profile.school.code if user.teacher_profile.school else ""
        prefix = f"{code}-"
        display_emp = emp[len(prefix):] if (code and emp.startswith(prefix)) else emp
        if new_password.lower() in (emp.lower(), display_emp.lower()):
            raise ValidationError({"newPassword": "New password cannot be your employee ID."})

    # Cannot be equal to user mobile
    if user.mobile and new_password == user.mobile:
        raise ValidationError({"newPassword": "New password cannot be your mobile number."})

    validate_password(new_password, user=user)

    user.set_password(new_password)
    user.save()

    sec, _ = UserSecurity.objects.get_or_create(user=user)
    sec.must_change_password = False
    sec.password_changed_at = timezone.now()
    sec.save()

    if request:
        update_session_auth_hash(request, user)

    # Resolve school for audit if available
    school = getattr(user, "school_administered", None)
    if not school and hasattr(user, "teacher_profile"):
        school = user.teacher_profile.school
    elif not school and hasattr(user, "student_profile"):
        school = user.student_profile.school

    log_action(
        actor=user,
        school=school,
        action="credentials.change_password",
        obj=user,
        changes={"must_change_password": False},
        request=request,
    )


def reissue_credentials_for_school(actor, school, scope, class_id=None, password_mode="random", request=None):
    """
    Reissues credentials for users in the active school who were created_via='import'
    AND still have must_change_password=True.
    Scopes: 'students' | 'teachers' | 'parents' | 'class'.
    Never touches parents or users who have already changed their passwords.
    Returns: (sheet_buffer, reissued_count, skipped_count)
    """
    credentials_rows = []
    skipped_count = 0

    with transaction.atomic():
        if scope in ("students", "class"):
            qs = Student.objects.filter(school=school).select_related("user", "school")
            if scope == "class":
                if not class_id:
                    raise ValidationError({"classId": "Class ID is required when scope is 'class'."})
                try:
                    s_class = SchoolClass.objects.get(pk=class_id, school=school)
                except SchoolClass.DoesNotExist:
                    raise ValidationError({"classId": "Class does not exist in your school."})
                qs = qs.filter(class_section=s_class)

            for student in qs.order_by("admission_number"):
                u = student.user
                sec = getattr(u, "security", None)
                if sec and sec.created_via == "import" and sec.must_change_password:
                    sg = StudentGuardian.objects.filter(student=student, is_primary=True).select_related("guardian").first()
                    g_mobile = sg.guardian.mobile if (sg and sg.guardian) else ""
                    disp_id = format_display_id(school.code, student.admission_number)
                    temp_pw = generate_password_for_mode(
                        password_mode,
                        "student",
                        display_id=disp_id,
                        mobile=g_mobile,
                        school_code=school.code,
                    )
                    u.set_password(temp_pw)
                    u.save()
                    sec.must_change_password = True
                    sec.save()
                    credentials_rows.append({
                        "role": "Student",
                        "name": u.get_full_name() or u.username,
                        "identifier": disp_id,
                        "username": u.username,
                        "password": temp_pw,
                        "notes": "Reissued credentials",
                    })
                else:
                    skipped_count += 1

        elif scope == "teachers":
            qs = Teacher.objects.filter(school=school).select_related("user", "school").order_by("employee_id")
            for teacher in qs:
                u = teacher.user
                sec = getattr(u, "security", None)
                if sec and sec.created_via == "import" and sec.must_change_password:
                    disp_id = format_display_id(school.code, teacher.employee_id)
                    temp_pw = generate_password_for_mode(
                        password_mode,
                        "teacher",
                        display_id=disp_id,
                        mobile=u.mobile,
                        school_code=school.code,
                    )
                    u.set_password(temp_pw)
                    u.save()
                    sec.must_change_password = True
                    sec.save()
                    credentials_rows.append({
                        "role": "Teacher",
                        "name": u.get_full_name() or u.username,
                        "identifier": disp_id,
                        "username": u.username,
                        "password": temp_pw,
                        "notes": "Reissued credentials",
                    })
                else:
                    skipped_count += 1

        elif scope == "parents":
            guardians = Guardian.objects.filter(school=school, user__isnull=False).select_related("user").order_by("id")
            seen_parent_ids = set()
            for g in guardians:
                u = g.user
                if u.id in seen_parent_ids:
                    continue
                seen_parent_ids.add(u.id)
                sec = getattr(u, "security", None)
                if sec and sec.created_via == "import" and sec.must_change_password:
                    temp_pw = generate_password_for_mode(
                        password_mode,
                        "parent",
                        display_id=u.username,
                        mobile=u.username,
                        school_code=school.code,
                    )
                    u.set_password(temp_pw)
                    u.save()
                    sec.must_change_password = True
                    sec.save()
                    credentials_rows.append({
                        "role": "Parent",
                        "name": u.get_full_name() or g.full_name or u.username,
                        "identifier": u.username,
                        "username": u.username,
                        "password": temp_pw,
                        "notes": "Reissued credentials",
                    })
                else:
                    skipped_count += 1
        else:
            raise ValidationError({"scope": f"Invalid scope '{scope}'. Allowed: students, teachers, parents, class."})

        log_action(
            actor=actor,
            school=school,
            action="credentials.reissue",
            changes={
                "scope": scope,
                "class_id": class_id,
                "reissued_count": len(credentials_rows),
                "skipped_count": skipped_count,
                "password_mode": password_mode,
            },
            request=request,
        )

    sheet_buffer = build_credentials_sheet(
        credentials_rows=credentials_rows,
        school_name=school.name,
        sheet_title=f"Reissued {scope.capitalize()}",
    )
    return sheet_buffer, len(credentials_rows), skipped_count


def build_credentials_sheet(credentials_rows, school_name="School", sheet_title="Credentials"):
    """
    Builds an in-memory openpyxl Workbook with credentials and returns io.BytesIO.
    credentials_rows is a list of dicts:
    [
        {
            "role": "Teacher",
            "name": "Ramesh Kumar",
            "identifier": "EMP-001",
            "username": "DPS09-T-EMP001",
            "password": "...",
            "notes": "Must change password on first login"
        },
        ...
    ]
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title

    # Header style
    brand_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Arial", size=14, bold=True, color="1E3A8A")
    regular_font = Font(name="Arial", size=10)
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="E5E7EB"),
        right=Side(style="thin", color="E5E7EB"),
        top=Side(style="thin", color="E5E7EB"),
        bottom=Side(style="thin", color="E5E7EB"),
    )

    # Row 1: Title
    ws.merge_cells("A1:F1")
    title_cell = ws["A1"]
    title_cell.value = f"{school_name} - Generated Account Credentials"
    title_cell.font = title_font
    title_cell.alignment = left_align
    ws.row_dimensions[1].height = 30

    # Row 2: Subtitle warning
    ws.merge_cells("A2:F2")
    sub_cell = ws["A2"]
    sub_cell.value = "CONFIDENTIAL: Download once and distribute securely. Plaintext passwords are not stored in the system."
    sub_cell.font = Font(name="Arial", size=9, italic=True, color="DC2626")
    sub_cell.alignment = left_align
    ws.row_dimensions[2].height = 20

    # Row 3: Blank separator
    ws.row_dimensions[3].height = 10

    # Row 4: Column Headers
    headers = ["Role", "Name", "ID / Admission No", "Username / Login ID", "Temporary Password", "Action Required"]
    for col_idx, header_text in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col_idx, value=header_text)
        cell.fill = brand_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = thin_border
    ws.row_dimensions[4].height = 24

    # Data Rows
    for row_idx, item in enumerate(credentials_rows, start=5):
        ws.row_dimensions[row_idx].height = 20
        row_values = [
            item.get("role", ""),
            item.get("name", ""),
            item.get("identifier", ""),
            item.get("username", ""),
            item.get("password", ""),
            item.get("notes", "Must change password on first login"),
        ]
        for col_idx, val in enumerate(row_values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=str(val) if val is not None else "")
            cell.font = regular_font
            cell.alignment = center_align if col_idx in (1, 3, 4) else left_align
            cell.border = thin_border

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            # Ignore merged cells in row 1 & 2 for width calculation
            if cell.row in (1, 2, 3):
                continue
            val_len = len(str(cell.value or ""))
            if val_len > max_len:
                max_len = val_len
        ws.column_dimensions[col_letter].width = max(max_len + 4, 15)

    ws.freeze_panes = "A5"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
