from rest_framework.permissions import BasePermission


class IsPrincipalOrSuperuser(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_superuser or getattr(u, "role", "") in ("principal", "admin")))


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, "role", "") == "teacher")
