from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    schoolId = serializers.IntegerField(source="school_id", read_only=True)
    actorId = serializers.IntegerField(source="actor_id", read_only=True)
    actorUsername = serializers.CharField(source="actor.username", read_only=True)
    actorRole = serializers.CharField(source="actor.role", read_only=True)
    objectType = serializers.CharField(source="object_type", read_only=True)
    objectId = serializers.IntegerField(source="object_id", read_only=True)
    ipAddress = serializers.CharField(source="ip_address", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "schoolId",
            "actorId",
            "actorUsername",
            "actorRole",
            "action",
            "objectType",
            "objectId",
            "changes",
            "ipAddress",
            "createdAt",
        ]
        read_only_fields = fields
