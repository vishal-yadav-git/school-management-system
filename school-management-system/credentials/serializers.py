from rest_framework import serializers


class ResetPasswordSerializer(serializers.Serializer):
    userId = serializers.IntegerField(required=True)


class ChangePasswordSerializer(serializers.Serializer):
    oldPassword = serializers.CharField(required=True, write_only=True)
    newPassword = serializers.CharField(required=True, write_only=True)
