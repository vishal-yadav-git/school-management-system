from rest_framework import serializers
from .models import ClassSubjectTeacher, TeacherPermission
from .services import VALID_PERMISSION_KEYS


class TeacherPermissionSerializer(serializers.ModelSerializer):
    permissionKey = serializers.CharField(source="permission_key")
    grantedAt = serializers.DateTimeField(source="granted_at")
    grantedBy = serializers.SerializerMethodField()

    class Meta:
        model = TeacherPermission
        fields = ["id", "permissionKey", "grantedAt", "grantedBy"]

    def get_grantedBy(self, obj):
        return obj.granted_by.get_full_name() if obj.granted_by else None


class GrantPermissionInputSerializer(serializers.Serializer):
    permissionKey = serializers.ChoiceField(choices=VALID_PERMISSION_KEYS)
    granted = serializers.BooleanField(required=True)


class ClassSubjectTeacherSerializer(serializers.ModelSerializer):
    classId = serializers.IntegerField(source="school_class.id")
    className = serializers.CharField(source="school_class.name")
    section = serializers.CharField(source="school_class.section")
    subjectId = serializers.IntegerField(source="subject.id")
    subjectName = serializers.CharField(source="subject.name")
    teacherId = serializers.IntegerField(source="teacher.id")
    teacherName = serializers.SerializerMethodField()

    class Meta:
        model = ClassSubjectTeacher
        fields = [
            "id",
            "classId",
            "className",
            "section",
            "subjectId",
            "subjectName",
            "teacherId",
            "teacherName",
            "assigned_at",
        ]

    def get_teacherName(self, obj):
        return obj.teacher.user.get_full_name() or obj.teacher.user.username


class AssignSubjectTeacherInputSerializer(serializers.Serializer):
    subjectId = serializers.IntegerField(required=True)
    teacherId = serializers.IntegerField(required=True)
