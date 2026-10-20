from rest_framework import serializers


class AttendanceRecordInputSerializer(serializers.Serializer):
    studentId = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["present", "absent", "late", "leave"])
    remark = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class AttendanceSessionInputSerializer(serializers.Serializer):
    date = serializers.DateField()
    records = serializers.ListField(
        child=AttendanceRecordInputSerializer(),
        allow_empty=False,
    )
