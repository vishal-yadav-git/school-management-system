from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from academics.models import Student, Teacher
from accounts.models import User
from api.permissions import IsPrincipalOrSuperuser
from guardians.models import Guardian
from organizations.models import SchoolOrganization
from organizations.services import get_active_school_for_user

from .serializers import ChangePasswordSerializer, ReissueCredentialsSerializer, ResetPasswordSerializer
from .services import change_user_password, reissue_credentials_for_school, reset_password_for_user


class PasswordResetThrottle(ScopedRateThrottle):
    scope = "password_reset"


class ReissueCredentialsThrottle(ScopedRateThrottle):
    scope = "credentials_reissue"


@api_view(["POST"])
@permission_classes([IsPrincipalOrSuperuser])
@throttle_classes([PasswordResetThrottle])
def principal_reset_password(request):
    """
    Principal resets password for a teacher, student, or guardian in their school.
    Enforces strict tenant isolation: rejects users from other schools.
    """
    serializer = ResetPasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user_id = serializer.validated_data["userId"]
    try:
        target_user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

    active_school = get_active_school_for_user(request)
    if not active_school and not request.user.is_superuser:
        return Response({"detail": "No active school found for your account."}, status=status.HTTP_400_BAD_REQUEST)

    # Superuser can reset anyone
    if not request.user.is_superuser:
        # Check if target_user belongs to active_school
        is_member = (
            Teacher.objects.filter(user=target_user, school=active_school).exists()
            or Student.objects.filter(user=target_user, school=active_school).exists()
            or Guardian.objects.filter(user=target_user, school=active_school).exists()
        )
        if not is_member:
            return Response(
                {"detail": "User does not belong to your school."},
                status=status.HTTP_403_FORBIDDEN,
            )

    temp_password = reset_password_for_user(
        actor=request.user,
        target_user=target_user,
        school=active_school,
        request=request,
    )

    return Response(
        {
            "username": target_user.username,
            "temporaryPassword": temp_password,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Authenticated user changes their own password.
    Clears must_change_password flag and updates session.
    """
    serializer = ChangePasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    old_password = serializer.validated_data["oldPassword"]
    new_password = serializer.validated_data["newPassword"]

    try:
        change_user_password(
            user=request.user,
            old_password=old_password,
            new_password=new_password,
            request=request,
        )
    except DjangoValidationError as exc:
        if hasattr(exc, "message_dict"):
            detail = exc.message_dict
        elif hasattr(exc, "messages"):
            detail = exc.messages[0] if len(exc.messages) == 1 else exc.messages
        else:
            detail = str(exc)
        return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsPrincipalOrSuperuser])
@throttle_classes([ReissueCredentialsThrottle])
def reissue_credentials_view(request):
    """
    Principal reissues credentials for users in their active school.
    Active school only, throttled.
    Only touches users created_via='import' AND must_change_password=True.
    Returns credentials xlsx as direct binary stream, Cache-Control: no-store.
    """
    active_school = get_active_school_for_user(request)
    if not active_school and not request.user.is_superuser:
        return Response({"detail": "No active school found for your account."}, status=status.HTTP_400_BAD_REQUEST)

    # Check if school email verification is pending
    if active_school:
        so = SchoolOrganization.objects.filter(school=active_school).first()
        if so and so.status == "pending":
            return Response(
                {
                    "detail": "School email verification is pending. Verify email to reissue credentials.",
                    "code": "EMAIL_VERIFICATION_PENDING",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

    serializer = ReissueCredentialsSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    scope = serializer.validated_data["scope"]
    class_id = serializer.validated_data.get("classId")
    password_mode = serializer.validated_data.get("passwordMode", "random")

    try:
        sheet_buffer, reissued_count, skipped_count = reissue_credentials_for_school(
            actor=request.user,
            school=active_school,
            scope=scope,
            class_id=class_id,
            password_mode=password_mode,
            request=request,
        )
    except DjangoValidationError as exc:
        if hasattr(exc, "message_dict"):
            detail = exc.message_dict
        elif hasattr(exc, "messages"):
            detail = exc.messages[0] if len(exc.messages) == 1 else exc.messages
        else:
            detail = str(exc)
        return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return Response({"detail": f"Failed to reissue credentials: {str(exc)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    timestamp_str = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reissued_{scope}_{timestamp_str}.xlsx"

    response = HttpResponse(
        sheet_buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Reissued-Count"] = str(reissued_count)
    response["X-Skipped-Count"] = str(skipped_count)
    response["Access-Control-Expose-Headers"] = "Content-Disposition, X-Reissued-Count, X-Skipped-Count"

    return response

