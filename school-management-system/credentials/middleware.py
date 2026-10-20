from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


class MustChangePasswordMiddleware(MiddlewareMixin):
    ALLOWED_PATHS = {
        "/api/v1/auth/change-password/",
        "/api/v1/auth/logout/",
        "/api/v1/auth/me/",
        "/api/v1/auth/csrf/",
    }

    def process_request(self, request):
        path = request.path

        # Only enforce on API routes
        if not path.startswith("/api/"):
            return None

        # Allow explicitly whitelisted paths
        if path in self.ALLOWED_PATHS:
            return None

        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            security = getattr(user, "security", None)
            if security and security.must_change_password:
                return JsonResponse(
                    {
                        "detail": "You must change your temporary password before proceeding.",
                        "code": "MUST_CHANGE_PASSWORD",
                    },
                    status=403,
                )

        return None
