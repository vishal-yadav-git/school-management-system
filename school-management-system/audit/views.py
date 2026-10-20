from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from api.permissions import IsPrincipalOrSuperuser
from api.views_admin import get_principal_school
from .models import AuditLog
from .serializers import AuditLogSerializer


@api_view(["GET"])
@permission_classes([IsPrincipalOrSuperuser])
def audit_logs(request):
    """
    GET audit/?action=&limit=50
    Principal views own school audit logs. Superuser views all or filtered by ?school=<id>.
    Read-only endpoint.
    """
    user = request.user
    if user.is_superuser:
        school_id = request.query_params.get("school")
        if school_id:
            queryset = AuditLog.objects.filter(school_id=school_id)
        else:
            queryset = AuditLog.objects.all()
    else:
        school = get_principal_school(user)
        queryset = AuditLog.objects.filter(school=school)

    action = request.query_params.get("action")
    if action:
        queryset = queryset.filter(action=action)

    try:
        limit = int(request.query_params.get("limit", 50))
        if limit <= 0:
            limit = 50
    except (ValueError, TypeError):
        limit = 50

    limit = min(limit, 100)
    logs = queryset.select_related("actor", "school")[:limit]
    serializer = AuditLogSerializer(logs, many=True)
    return Response(serializer.data)
