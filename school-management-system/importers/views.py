import secrets
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from api.permissions import IsPrincipalOrSuperuser
from credentials.services import build_credentials_sheet
from organizations.models import SchoolOrganization
from organizations.services import get_active_school_for_user

from .services import (
    commit_student_import,
    commit_teacher_import,
    generate_student_template,
    generate_teacher_template,
    validate_student_import,
    validate_teacher_import,
)


class ImportPreviewThrottle(ScopedRateThrottle):
    scope = "import_preview"


class ImportConfirmThrottle(ScopedRateThrottle):
    scope = "import_confirm"


@api_view(["GET"])
@permission_classes([IsPrincipalOrSuperuser])
def teacher_template_download(request):
    """
    Downloads an Excel template for teacher bulk import.
    """
    buffer = generate_teacher_template()
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="teacher_import_template.xlsx"'
    return response


@api_view(["GET"])
@permission_classes([IsPrincipalOrSuperuser])
def student_template_download(request):
    """
    Downloads an Excel template for student bulk import.
    """
    buffer = generate_student_template()
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="student_import_template.xlsx"'
    return response


@api_view(["POST"])
@permission_classes([IsPrincipalOrSuperuser])
@parser_classes([MultiPartParser, FormParser])
@throttle_classes([ImportPreviewThrottle])
def import_preview(request):
    """
    Validates teacher or student excel import (Dry Run).
    Returns row-level errors and caches valid rows under a secure single-use importToken.
    """
    active_school = get_active_school_for_user(request)
    if not active_school and not request.user.is_superuser:
        return Response({"detail": "No active school found for your account."}, status=status.HTTP_400_BAD_REQUEST)

    import_type = (request.data.get("type") or "").strip().lower()
    if import_type not in ("teacher", "student"):
        return Response(
            {"detail": "Parameter 'type' must be either 'teacher' or 'student'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    file_obj = request.FILES.get("file")
    if not file_obj:
        return Response({"detail": "No file uploaded. Key 'file' is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not file_obj.name.lower().endswith(".xlsx"):
        return Response({"detail": "Invalid file format. Only .xlsx files are supported."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        if import_type == "teacher":
            valid_rows, errors, total_rows = validate_teacher_import(file_obj, active_school)
        else:
            valid_rows, errors, total_rows = validate_student_import(file_obj, active_school)
    except DjangoValidationError as exc:
        msg = exc.messages if hasattr(exc, "messages") else str(exc)
        return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return Response({"detail": f"Failed to parse Excel file: {str(exc)}"}, status=status.HTTP_400_BAD_REQUEST)

    # Generate secure import token and cache payload for 30 minutes
    import_token = secrets.token_urlsafe(32)
    cache.set(
        f"import_preview_{import_token}",
        {
            "user_id": request.user.id,
            "school_id": active_school.id,
            "type": import_type,
            "valid_rows": valid_rows,
            "total_rows": total_rows,
            "error_rows": len(errors),
        },
        timeout=1800,
    )

    return Response(
        {
            "importToken": import_token,
            "type": import_type,
            "totalRows": total_rows,
            "validRows": len(valid_rows),
            "errorRows": len(errors),
            "errors": errors,
            "preview": valid_rows[:10],
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsPrincipalOrSuperuser])
@throttle_classes([ImportConfirmThrottle])
def import_confirm(request):
    """
    Confirms and executes the bulk import inside an atomic transaction.
    Blocks if school email verification is pending.
    Returns direct binary stream of credentials .xlsx with Cache-Control: no-store.
    """
    active_school = get_active_school_for_user(request)
    if not active_school and not request.user.is_superuser:
        return Response({"detail": "No active school found for your account."}, status=status.HTTP_400_BAD_REQUEST)

    # Guard: check if active school is pending email verification
    so = SchoolOrganization.objects.filter(school=active_school).first()
    if so and so.status == "pending":
        return Response(
            {
                "detail": "School email verification is pending. Verify your email to complete import.",
                "code": "EMAIL_VERIFICATION_PENDING",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    import_token = request.data.get("importToken")
    if not import_token:
        return Response({"detail": "Field 'importToken' is required."}, status=status.HTTP_400_BAD_REQUEST)

    cache_key = f"import_preview_{import_token}"
    cached_data = cache.get(cache_key)
    if not cached_data:
        return Response({"detail": "Invalid or expired import token."}, status=status.HTTP_400_BAD_REQUEST)

    # Validate that token belongs to this user and school
    if cached_data.get("user_id") != request.user.id or cached_data.get("school_id") != active_school.id:
        return Response({"detail": "Import token is not valid for this user or campus."}, status=status.HTTP_403_FORBIDDEN)

    # Invalidate token immediately to prevent replay
    cache.delete(cache_key)

    valid_rows = cached_data.get("valid_rows", [])
    import_type = cached_data.get("type")
    password_mode = str(request.data.get("passwordMode") or "random").strip().lower()
    if password_mode not in ("random", "id_pattern"):
        password_mode = "random"

    if not valid_rows:
        return Response({"detail": "No valid rows to import."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        if import_type == "teacher":
            credentials_rows = commit_teacher_import(
                valid_rows=valid_rows,
                actor=request.user,
                school=active_school,
                password_mode=password_mode,
                request=request,
            )
        else:
            credentials_rows = commit_student_import(
                valid_rows=valid_rows,
                actor=request.user,
                school=active_school,
                password_mode=password_mode,
                request=request,
            )
    except Exception as exc:
        return Response({"detail": f"Import failed: {str(exc)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Build credentials Excel sheet in memory
    sheet_buffer = build_credentials_sheet(
        credentials_rows=credentials_rows,
        school_name=active_school.name,
        sheet_title=f"{import_type.capitalize()} Credentials",
    )

    timestamp_str = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"credentials_{import_type}_{timestamp_str}.xlsx"

    response = HttpResponse(
        sheet_buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Access-Control-Expose-Headers"] = "Content-Disposition"

    return response

