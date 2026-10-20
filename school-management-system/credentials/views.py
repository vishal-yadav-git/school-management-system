from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from academics.models import Student, Teacher
from accounts.models import User
from api.permissions import IsPrincipalOrSuperuser
from guardians.models import Guardian
from organizations.services import get_active_school_for_user

from .serializers import ChangePasswordSerializer, ResetPasswordSerializer
from .services import change_user_password, reset_password_for_user


class PasswordResetThrottle(ScopedRateThrottle):
    scope = "password_reset"


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
        msg = exc.messages if hasattr(exc, "messages") else str(exc)
        return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)
