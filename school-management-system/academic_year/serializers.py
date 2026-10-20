from rest_framework import serializers
from .models import AcademicYear


class AcademicYearSerializer(serializers.ModelSerializer):
    schoolId = serializers.IntegerField(source="school_id", read_only=True)
    schoolName = serializers.CharField(source="school.name", read_only=True)
    startDate = serializers.DateField(source="start_date")
    endDate = serializers.DateField(source="end_date")
    isCurrent = serializers.BooleanField(source="is_current", default=False)

    class Meta:
        model = AcademicYear
        fields = [
            "id",
            "schoolId",
            "schoolName",
            "name",
            "startDate",
            "endDate",
            "isCurrent",
        ]

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        if start_date and end_date and end_date <= start_date:
            raise serializers.ValidationError({"endDate": ["End date must be after start date."]})
        return attrs
