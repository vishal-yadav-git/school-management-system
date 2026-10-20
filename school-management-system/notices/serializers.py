from rest_framework import serializers
from .models import Notice


class NoticeSerializer(serializers.ModelSerializer):
    schoolId = serializers.IntegerField(source="school_id", read_only=True)
    schoolName = serializers.CharField(source="school.name", read_only=True)
    isPinned = serializers.BooleanField(source="is_pinned")
    expiresOn = serializers.DateField(source="expires_on", allow_null=True)
    targetClassIds = serializers.SerializerMethodField()
    targetClassNames = serializers.SerializerMethodField()
    createdById = serializers.IntegerField(source="created_by_id", read_only=True)
    createdByName = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = Notice
        fields = [
            "id",
            "schoolId",
            "schoolName",
            "title",
            "body",
            "audience",
            "targetClassIds",
            "targetClassNames",
            "isPinned",
            "expiresOn",
            "createdById",
            "createdByName",
            "createdAt",
            "updatedAt",
        ]

    def get_targetClassIds(self, obj):
        return list(obj.target_classes.values_list("id", flat=True))

    def get_targetClassNames(self, obj):
        return [f"{c.name}-{c.section}" for c in obj.target_classes.all()]

    def get_createdByName(self, obj):
        if not obj.created_by:
            return "System"
        return obj.created_by.get_full_name() or obj.created_by.username


class NoticeCreateInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    body = serializers.CharField()
    audience = serializers.ChoiceField(choices=["all", "parents", "teachers", "classes"], default="all")
    targetClassIds = serializers.ListField(child=serializers.IntegerField(), required=False, default=[])
    isPinned = serializers.BooleanField(required=False, default=False)
    expiresOn = serializers.DateField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if attrs.get("audience") == "classes" and not attrs.get("targetClassIds"):
            raise serializers.ValidationError({"targetClassIds": ["targetClassIds required when audience is 'classes'."]})
        return attrs


class NoticeUpdateInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    body = serializers.CharField(required=False)
    audience = serializers.ChoiceField(choices=["all", "parents", "teachers", "classes"], required=False)
    targetClassIds = serializers.ListField(child=serializers.IntegerField(), required=False)
    isPinned = serializers.BooleanField(required=False)
    expiresOn = serializers.DateField(required=False, allow_null=True)
