from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academics.models import Subject
from organizations.services import get_active_school_for_user

from .models import Topic, Unit
from .serializers import (
    CreateTopicInputSerializer,
    CreateUnitInputSerializer,
    TopicSerializer,
    UnitSerializer,
    UpdateTopicStatusInputSerializer,
)
from .services import (
    can_user_edit_syllabus,
    can_user_update_topic_status,
    can_user_view_syllabus,
)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def subject_syllabus_view(request, subject_id):
    """
    GET /api/v1/subjects/<id>/syllabus/
    Returns full unit and topic structure for a subject.
    Accessible to principal, teachers, students, and parents of that school.
    """
    subject = get_object_or_404(Subject, pk=subject_id)

    if not can_user_view_syllabus(request.user, subject):
        return Response({"detail": "You do not have access to this syllabus."}, status=status.HTTP_403_FORBIDDEN)

    units = Unit.objects.filter(subject=subject).prefetch_related("topics")
    return Response(UnitSerializer(units, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_unit_view(request, subject_id):
    """
    POST /api/v1/subjects/<id>/units/
    Adds a new unit to a subject.
    Permitted for principal or teachers with manage_syllabus or assigned to the subject.
    """
    subject = get_object_or_404(Subject, pk=subject_id)

    if not can_user_edit_syllabus(request.user, subject):
        return Response({"detail": "You do not have permission to modify syllabus for this subject."}, status=status.HTTP_403_FORBIDDEN)

    serializer = CreateUnitInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    unit_number = serializer.validated_data["unitNumber"]
    title = serializer.validated_data["title"]
    description = serializer.validated_data["description"]

    if Unit.objects.filter(subject=subject, unit_number=unit_number).exists():
        return Response(
            {"unitNumber": [f"Unit number {unit_number} already exists for this subject."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    unit = Unit.objects.create(
        subject=subject,
        unit_number=unit_number,
        title=title,
        description=description,
    )

    return Response(UnitSerializer(unit).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_topic_view(request, unit_id):
    """
    POST /api/v1/units/<id>/topics/
    Adds a new topic to a unit.
    Permitted for principal or teachers with manage_syllabus or assigned to the subject.
    """
    unit = get_object_or_404(Unit, pk=unit_id)

    if not can_user_edit_syllabus(request.user, unit.subject):
        return Response({"detail": "You do not have permission to modify syllabus for this subject."}, status=status.HTTP_403_FORBIDDEN)

    serializer = CreateTopicInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    topic_number = serializer.validated_data["topicNumber"]
    title = serializer.validated_data["title"]
    description = serializer.validated_data["description"]

    if Topic.objects.filter(unit=unit, topic_number=topic_number).exists():
        return Response(
            {"topicNumber": [f"Topic number {topic_number} already exists for this unit."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    topic = Topic.objects.create(
        unit=unit,
        topic_number=topic_number,
        title=title,
        description=description,
        status="not_started",
    )

    return Response(TopicSerializer(topic).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_topic_status_view(request, topic_id):
    """
    PATCH /api/v1/topics/<id>/status/
    Updates topic completion status ('not_started', 'in_progress', 'completed').
    Permitted for principal or assigned teachers. Students/parents are rejected with 403.
    """
    topic = get_object_or_404(Topic, pk=topic_id)

    if not can_user_update_topic_status(request.user, topic):
        return Response({"detail": "You do not have permission to update status for this topic."}, status=status.HTTP_403_FORBIDDEN)

    serializer = UpdateTopicStatusInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    new_status = serializer.validated_data["status"]
    topic.status = new_status
    if new_status == "completed":
        topic.completed_at = timezone.now()
    else:
        topic.completed_at = None
    topic.save()

    return Response(TopicSerializer(topic).data, status=status.HTTP_200_OK)
