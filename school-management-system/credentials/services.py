import io
import re
import secrets
import string
from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from accounts.models import User
from audit.services import log_action
from .models import UserSecurity


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
    Changes a user's password, validates password complexity,
    clears must_change_password, and updates session auth hash.
    """
    if not user.check_password(old_password):
        raise ValidationError({"oldPassword": "Old password is incorrect."})

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
