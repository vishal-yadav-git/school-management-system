from rest_framework import serializers


class ResetPasswordSerializer(serializers.Serializer):
    userId = serializers.IntegerField(required=True)


class ChangePasswordSerializer(serializers.Serializer):
    oldPassword = serializers.CharField(required=True, write_only=True)
    newPassword = serializers.CharField(required=True, write_only=True)


class ReissueCredentialsSerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=["students", "teachers", "parents", "class"], required=True)
    classId = serializers.IntegerField(required=False, allow_null=True)
    passwordMode = serializers.ChoiceField(choices=["random", "id_pattern"], required=False, default="random")
