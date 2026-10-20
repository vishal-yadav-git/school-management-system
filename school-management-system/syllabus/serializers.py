from rest_framework import serializers
from .models import Topic, Unit


class TopicSerializer(serializers.ModelSerializer):
    topicNumber = serializers.IntegerField(source="topic_number")
    completedAt = serializers.DateTimeField(source="completed_at", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Topic
        fields = [
            "id",
            "topicNumber",
            "title",
            "description",
            "status",
            "completedAt",
            "createdAt",
        ]


class UnitSerializer(serializers.ModelSerializer):
    unitNumber = serializers.IntegerField(source="unit_number")
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    topics = TopicSerializer(many=True, read_only=True)

    class Meta:
        model = Unit
        fields = [
            "id",
            "unitNumber",
            "title",
            "description",
            "createdAt",
            "topics",
        ]


class CreateUnitInputSerializer(serializers.Serializer):
    unitNumber = serializers.IntegerField(required=True, min_value=1)
    title = serializers.CharField(required=True, max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class CreateTopicInputSerializer(serializers.Serializer):
    topicNumber = serializers.IntegerField(required=True, min_value=1)
    title = serializers.CharField(required=True, max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class UpdateTopicStatusInputSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["not_started", "in_progress", "completed"])
