from rest_framework import exceptions
from rest_framework.permissions import BasePermission


class MustChangePasswordPermission(BasePermission):
    ALLOWED_PATHS = {
        "/api/v1/auth/change-password/",
        "/api/v1/auth/logout/",
        "/api/v1/auth/me/",
        "/api/v1/auth/csrf/",
    }

    def has_permission(self, request, view):
        if request.path in self.ALLOWED_PATHS:
            return True

        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            security = getattr(user, "security", None)
            if security and security.must_change_password:
                raise exceptions.PermissionDenied(
                    {
                        "detail": "You must change your temporary password before proceeding.",
                        "code": "MUST_CHANGE_PASSWORD",
                    }
                )

        return True
