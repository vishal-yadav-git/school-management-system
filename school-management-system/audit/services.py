from .models import AuditLog


def get_client_ip(request):
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_action(actor, school, action, obj=None, changes=None, request=None):
    object_type = ""
    object_id = None
    if obj is not None:
        object_type = obj.__class__.__name__
        object_id = getattr(obj, "pk", None)

    ip_address = get_client_ip(request)

    return AuditLog.objects.create(
        school=school,
        actor=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
        action=action,
        object_type=object_type,
        object_id=object_id,
        changes=changes or {},
        ip_address=ip_address,
    )
