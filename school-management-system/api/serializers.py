from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
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
        fields = ["id", "username", "firstName", "lastName", "email", "role", "isSuperuser", "mobile"]


class SchoolSerializer(serializers.ModelSerializer):
    principalName = serializers.SerializerMethodField()
    principalUsername = serializers.SerializerMethodField()
    totalStudents = serializers.SerializerMethodField()
    totalTeachers = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = [
            "id",
            "name",
            "code",
            "address",
            "city",
            "phone",
            "email",
            "principal",
            "principalName",
            "principalUsername",
            "totalStudents",
            "totalTeachers",
        ]

    def get_principalName(self, obj):
        return obj.principal.get_full_name() if obj.principal else None

    def get_principalUsername(self, obj):
        return obj.principal.username if obj.principal else None

    def get_totalStudents(self, obj):
        return getattr(obj, "students_count", None) or obj.students.count()

    def get_totalTeachers(self, obj):
        return getattr(obj, "teachers_count", None) or obj.teachers.count()


class PrincipalSerializer(serializers.ModelSerializer):
    schoolId = serializers.SerializerMethodField()
    schoolName = serializers.SerializerMethodField()
    fullName = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "fullName",
            "email",
            "mobile",
            "schoolId",
            "schoolName",
            "is_active",
            "date_joined",
        ]

    def get_schoolId(self, obj):
        return obj.principal_school.id if hasattr(obj, "principal_school") and obj.principal_school else None

    def get_schoolName(self, obj):
        return obj.principal_school.name if hasattr(obj, "principal_school") and obj.principal_school else None


class TeacherSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.get_full_name", read_only=True)
    firstName = serializers.CharField(source="user.first_name", read_only=True)
    lastName = serializers.CharField(source="user.last_name", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    mobile = serializers.CharField(source="user.mobile", read_only=True)
    employeeId = serializers.CharField(source="employee_id", read_only=True)
    schoolName = serializers.CharField(source="school.name", read_only=True)

    class Meta:
        model = Teacher
        fields = [
            "id",
            "name",
            "firstName",
            "lastName",
            "username",
            "email",
            "mobile",
            "employeeId",
            "designation",
            "qualification",
            "joining_date",
            "school",
            "schoolName",
        ]


class ClassSerializer(serializers.ModelSerializer):
    classTeacher = serializers.PrimaryKeyRelatedField(source="class_teacher", read_only=True)
    classTeacherName = serializers.SerializerMethodField()
    studentCount = serializers.SerializerMethodField()
    schoolName = serializers.CharField(source="school.name", read_only=True)

    class Meta:
        model = SchoolClass
        fields = [
            "id",
            "name",
            "section",
            "school",
            "schoolName",
            "classTeacher",
            "classTeacherName",
            "studentCount",
        ]

    def get_classTeacherName(self, obj):
        return obj.class_teacher.user.get_full_name() if obj.class_teacher and obj.class_teacher.user else None

    def get_studentCount(self, obj):
        return obj.students.count()


class StudentSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.get_full_name", read_only=True)
    firstName = serializers.CharField(source="user.first_name", read_only=True)
    lastName = serializers.CharField(source="user.last_name", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    mobile = serializers.CharField(source="user.mobile", read_only=True)
    admissionNumber = serializers.CharField(source="admission_number", read_only=True)
    classSection = serializers.PrimaryKeyRelatedField(source="class_section", read_only=True)
    className = serializers.SerializerMethodField()
    schoolName = serializers.CharField(source="school.name", read_only=True)

    class Meta:
        model = Student
        fields = [
            "id",
            "name",
            "firstName",
            "lastName",
            "username",
            "email",
            "mobile",
            "admissionNumber",
            "gender",
            "date_of_birth",
            "address",
            "admission_date",
            "school",
            "schoolName",
            "classSection",
            "className",
        ]

    def get_className(self, obj):
        c = obj.class_section
        return f"{c.name}-{c.section}" if c else None


class RegisterSerializer(serializers.Serializer):
    role = serializers.CharField(required=False, default="parent")
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    firstName = serializers.CharField(required=False, allow_blank=True, default="")
    lastName = serializers.CharField(required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    mobile = serializers.CharField(required=False, allow_blank=True, default="")
    schoolId = serializers.IntegerField(required=False, allow_null=True)
    admissionNumber = serializers.CharField(required=False, allow_blank=True, default="")
    employeeId = serializers.CharField(required=False, allow_blank=True, default="")
    gender = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        role_raw = attrs.get("role", "parent")
        role = role_raw.lower().strip() if role_raw else "parent"
        attrs["role"] = role

        if role not in ("student", "parent", "teacher"):
            raise serializers.ValidationError({"role": ["This role cannot be registered publicly"]})

        username = attrs.get("username", "").strip()
        attrs["username"] = username
        if not username:
            raise serializers.ValidationError({"username": ["This field is required."]})
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError({"username": ["A user with that username already exists."]})

        password = attrs.get("password")
        if not password:
            raise serializers.ValidationError({"password": ["This field is required."]})
        try:
            validate_password(password)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})

        email = attrs.get("email", "").strip()
        attrs["email"] = email
        if email and User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({"email": ["A user with that email already exists."]})

        mobile = attrs.get("mobile", "").strip()
        attrs["mobile"] = mobile
        if mobile and User.objects.filter(mobile=mobile).exists():
            raise serializers.ValidationError({"mobile": ["A user with that mobile number already exists."]})

        if role in ("student", "teacher"):
            school_id = attrs.get("schoolId")
            if not school_id:
                raise serializers.ValidationError({"schoolId": ["This field is required."]})
            try:
                school = School.objects.get(pk=school_id)
                attrs["_school"] = school
            except School.DoesNotExist:
                raise serializers.ValidationError({"schoolId": ["School does not exist."]})

        if role == "student":
            adm = attrs.get("admissionNumber", "").strip()
            attrs["admissionNumber"] = adm
            if not adm:
                raise serializers.ValidationError({"admissionNumber": ["This field is required."]})
            if Student.objects.filter(admission_number__iexact=adm).exists():
                raise serializers.ValidationError({"admissionNumber": ["A student with that admission number already exists."]})

        if role == "teacher":
            emp = attrs.get("employeeId", "").strip()
            attrs["employeeId"] = emp
            if not emp:
                raise serializers.ValidationError({"employeeId": ["This field is required."]})
            if Teacher.objects.filter(employee_id__iexact=emp).exists():
                raise serializers.ValidationError({"employeeId": ["A teacher with that employee ID already exists."]})

        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            user = User(
                username=validated_data["username"],
                email=validated_data.get("email", ""),
                mobile=validated_data.get("mobile", ""),
                first_name=validated_data.get("firstName", ""),
                last_name=validated_data.get("lastName", ""),
                role=validated_data["role"],
                is_staff=False,
                is_superuser=False,
                is_active=True,
            )
            user.set_password(validated_data["password"])
            user.save()

            if user.role == "student":
                Student.objects.create(
                    user=user,
                    school=validated_data["_school"],
                    admission_number=validated_data["admissionNumber"],
                    gender=validated_data.get("gender", ""),
                )
            elif user.role == "teacher":
                Teacher.objects.create(
                    user=user,
                    school=validated_data["_school"],
                    employee_id=validated_data["employeeId"],
                )
            return user

