from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import User
from .models import Organization, SchoolOrganization


class RegisterOrgSerializer(serializers.Serializer):
    organizationName = serializers.CharField(required=True, max_length=200)
    campusName = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")
    username = serializers.CharField(required=True, max_length=150)
    email = serializers.EmailField(required=True)
    mobile = serializers.CharField(required=False, allow_blank=True, max_length=15, default="")
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        org_name = attrs.get("organizationName", "").strip()
        username = attrs.get("username", "").strip()
        email = attrs.get("email", "").strip()
        password = attrs.get("password", "")

        if not org_name:
            raise serializers.ValidationError({"organizationName": ["Organization name is required."]})

        if not username:
            raise serializers.ValidationError({"username": ["Username is required."]})

        if not email:
            raise serializers.ValidationError({"email": ["Email address is required."]})

        # Generic rejection to prevent user enumeration
        if User.objects.filter(username__iexact=username).exists() or User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                {"detail": "An account with these details could not be registered. Please check your information or sign in."}
            )

        try:
            validate_password(password)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})

        attrs["organizationName"] = org_name
        attrs["username"] = username
        attrs["email"] = email
        return attrs


class CampusSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="school.id", read_only=True)
    name = serializers.CharField(source="school.name", read_only=True)
    code = serializers.CharField(source="school.code", read_only=True)
    city = serializers.CharField(source="school.city", read_only=True)
    status = serializers.CharField(read_only=True)
    isMainCampus = serializers.BooleanField(source="is_main_campus", read_only=True)
    isCurrent = serializers.SerializerMethodField()

    class Meta:
        model = SchoolOrganization
        fields = [
            "id",
            "name",
            "code",
            "city",
            "status",
            "isMainCampus",
            "isCurrent",
        ]

    def get_isCurrent(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        active_id = request.session.get("active_school_id")
        return obj.school.id == active_id


class OrganizationSerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Organization
        fields = ["id", "name", "code", "createdAt"]
