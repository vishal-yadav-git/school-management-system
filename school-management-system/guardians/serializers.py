from rest_framework import serializers
from .models import Guardian, StudentGuardian


class StudentGuardianSerializer(serializers.ModelSerializer):
    guardianId = serializers.IntegerField(source="guardian.id", read_only=True)
    fullName = serializers.CharField(source="guardian.full_name", read_only=True)
    mobile = serializers.CharField(source="guardian.mobile", read_only=True)
    email = serializers.CharField(source="guardian.email", read_only=True)
    relation = serializers.CharField()
    isPrimary = serializers.BooleanField(source="is_primary")
    linkStatus = serializers.CharField(source="guardian.link_status", read_only=True)
    linkedUsername = serializers.CharField(source="guardian.user.username", default=None, read_only=True)

    class Meta:
        model = StudentGuardian
        fields = [
            "id",
            "guardianId",
            "fullName",
            "mobile",
            "email",
            "relation",
            "isPrimary",
            "linkStatus",
            "linkedUsername",
        ]


class AddGuardianSerializer(serializers.Serializer):
    fullName = serializers.CharField(max_length=150)
    mobile = serializers.CharField(max_length=15)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    relation = serializers.ChoiceField(
        choices=[("father", "father"), ("mother", "mother"), ("guardian", "guardian"), ("other", "other")],
        default="guardian",
    )
    isPrimary = serializers.BooleanField(default=False)


class GuardianLinkRequestSerializer(serializers.ModelSerializer):
    guardianName = serializers.CharField(source="full_name", read_only=True)
    guardianMobile = serializers.CharField(source="mobile", read_only=True)
    requestedUser = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Guardian
        fields = [
            "id",
            "guardianName",
            "guardianMobile",
            "requestedUser",
            "children",
        ]

    def get_requestedUser(self, obj):
        u = obj.requested_user
        if not u:
            return None
        return {
            "id": u.id,
            "username": u.username,
            "name": u.get_full_name() or u.username,
            "mobile": getattr(u, "mobile", ""),
        }

    def get_children(self, obj):
        res = []
        for sg in obj.guardian_students.select_related("student__user", "student__class_section"):
            s = sg.student
            c_name = f"{s.class_section.name}-{s.class_section.section}" if s.class_section else "Unassigned"
            res.append({
                "id": s.id,
                "name": s.user.get_full_name() or s.user.username,
                "className": c_name,
            })
        return res


class ParentChildSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    admissionNumber = serializers.CharField()
    schoolId = serializers.IntegerField()
    schoolName = serializers.CharField()
    className = serializers.CharField()
    todayStatus = serializers.CharField()
