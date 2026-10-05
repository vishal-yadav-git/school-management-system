from rest_framework import serializers

from academics.models import SchoolClass, Student, Teacher
from accounts.models import User
from schools.models import School


class UserSerializer(serializers.ModelSerializer):
    firstName = serializers.CharField(source="first_name", read_only=True)
    lastName = serializers.CharField(source="last_name", read_only=True)
    isSuperuser = serializers.BooleanField(source="is_superuser", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "firstName", "lastName", "email", "role", "isSuperuser"]


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["id", "name", "code", "address", "city", "phone", "email"]


class TeacherSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.get_full_name", read_only=True)
    employeeId = serializers.CharField(source="employee_id", read_only=True)

    class Meta:
        model = Teacher
        fields = ["id", "name", "employeeId", "designation", "qualification", "school"]


class ClassSerializer(serializers.ModelSerializer):
    classTeacher = serializers.PrimaryKeyRelatedField(source="class_teacher", read_only=True)

    class Meta:
        model = SchoolClass
        fields = ["id", "name", "section", "school", "classTeacher"]


class StudentSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.get_full_name", read_only=True)
    admissionNumber = serializers.CharField(source="admission_number", read_only=True)
    classSection = serializers.PrimaryKeyRelatedField(source="class_section", read_only=True)
    className = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = ["id", "name", "admissionNumber", "gender", "school", "classSection", "className"]

    def get_className(self, obj):
        c = obj.class_section
        return f"{c.name}-{c.section}" if c else None
