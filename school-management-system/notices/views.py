from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academics.models import SchoolClass
from api.permissions import IsPrincipalOrSuperuser
from api.views_admin import get_principal_school, get_target_school
from audit.services import log_action
from .models import Notice
from .serializers import (
    NoticeCreateInputSerializer,
    NoticeSerializer,
    NoticeUpdateInputSerializer,
)
from .services import get_visible_notices_for_user


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def notices_list(request):
    """
    GET /api/v1/notices/
    POST /api/v1/notices/ (Principal or Superuser only)
    """
    user = request.user

    if request.method == "GET":
        school_id = request.query_params.get("school")
        qs = get_visible_notices_for_user(user, school_id=school_id)
        limit = request.query_params.get("limit")
        if limit:
            try:
                lim = int(limit)
                qs = qs[:lim]
            except ValueError:
                pass
        serializer = NoticeSerializer(qs, many=True)
        return Response(serializer.data)

    elif request.method == "POST":
        if not (user.is_superuser or getattr(user, "role", "") in ("principal", "admin")):
            raise PermissionDenied("Only principals or administrators can publish notices.")

        school = get_target_school(request)
        serializer = NoticeCreateInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        target_class_ids = data.get("targetClassIds", [])

        # Validate target classes belong to this school
        target_classes = []
        if target_class_ids:
            target_classes = list(SchoolClass.objects.filter(school=school, id__in=target_class_ids))
            if len(target_classes) != len(target_class_ids):
                return Response(
                    {"targetClassIds": ["Some target classes do not belong to this school."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            notice = Notice.objects.create(
                school=school,
                title=data["title"],
                body=data["body"],
                audience=data.get("audience", "all"),
                is_pinned=data.get("isPinned", False),
                expires_on=data.get("expiresOn"),
                created_by=user,
            )
            if target_classes:
                notice.target_classes.set(target_classes)

            log_action(
                actor=user,
                school=school,
                action="notice.create",
                obj=notice,
                changes={
                    "title": notice.title,
                    "audience": notice.audience,
                    "isPinned": notice.is_pinned,
                },
                request=request,
            )

        return Response(NoticeSerializer(notice).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def notice_detail(request, pk):
    """
    GET /api/v1/notices/<id>/
    PATCH /api/v1/notices/<id>/ (Principal or Superuser)
    DELETE /api/v1/notices/<id>/ (Principal or Superuser)
    """
    notice = get_object_or_404(Notice, id=pk)
    user = request.user

    if request.method == "GET":
        serializer = NoticeSerializer(notice)
        return Response(serializer.data)

    # For PATCH and DELETE, check principal / superuser permission
    if not (user.is_superuser or getattr(user, "role", "") in ("principal", "admin")):
        raise PermissionDenied("Only principals or administrators can modify notices.")

    if not user.is_superuser:
        school = get_principal_school(user)
        if notice.school_id != school.id:
            raise PermissionDenied("You do not have permission for this school's notices.")

    if request.method == "PATCH":
        serializer = NoticeUpdateInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        before_state = {
            "title": notice.title,
            "body": notice.body,
            "audience": notice.audience,
            "isPinned": notice.is_pinned,
            "expiresOn": str(notice.expires_on) if notice.expires_on else None,
        }

        with transaction.atomic():
            if "title" in data:
                notice.title = data["title"]
            if "body" in data:
                notice.body = data["body"]
            if "audience" in data:
                notice.audience = data["audience"]
            if "isPinned" in data:
                notice.is_pinned = data["isPinned"]
            if "expiresOn" in data:
                notice.expires_on = data["expiresOn"]

            if "targetClassIds" in data:
                target_class_ids = data["targetClassIds"]
                target_classes = list(SchoolClass.objects.filter(school=notice.school, id__in=target_class_ids))
                if len(target_classes) != len(target_class_ids):
                    return Response(
                        {"targetClassIds": ["Some target classes do not belong to this school."]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                notice.target_classes.set(target_classes)

            notice.save()

            after_state = {
                "title": notice.title,
                "body": notice.body,
                "audience": notice.audience,
                "isPinned": notice.is_pinned,
                "expiresOn": str(notice.expires_on) if notice.expires_on else None,
            }

            log_action(
                actor=user,
                school=notice.school,
                action="notice.update",
                obj=notice,
                changes={"before": before_state, "after": after_state},
                request=request,
            )

        return Response(NoticeSerializer(notice).data, status=status.HTTP_200_OK)

    elif request.method == "DELETE":
        with transaction.atomic():
            log_action(
                actor=user,
                school=notice.school,
                action="notice.delete",
                obj=notice,
                changes={"title": notice.title},
                request=request,
            )
            notice.delete()

        return Response({"detail": "Notice deleted successfully."}, status=status.HTTP_200_OK)
