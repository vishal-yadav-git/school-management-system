import re
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
    mustChangePassword = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "firstName", "lastName", "email", "role", "isSuperuser", "mobile", "mustChangePassword"]

    def get_mustChangePassword(self, obj):
        sec = getattr(obj, "security", None)
        return bool(sec.must_change_password) if sec else False


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
    employeeId = serializers.SerializerMethodField()
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

    def get_employeeId(self, obj):
        code = obj.school.code if obj.school else ""
        val = obj.employee_id or ""
        prefix = f"{code}-"
        if code and val.startswith(prefix):
            return val[len(prefix):]
        return val


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

    def validate_name(self, value):
        if value and re.match(r"^class(?:\b|\d)", value.strip(), flags=re.IGNORECASE):
            raise serializers.ValidationError("Do not prefix class name with 'Class'. Enter only standard/grade (e.g. '10' or 'X').")
        return value

    def validate_section(self, value):
        if value and "," in value:
            raise serializers.ValidationError("Section cannot contain commas. Create separate classes for each section.")
        return value


class StudentSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.get_full_name", read_only=True)
    firstName = serializers.CharField(source="user.first_name", read_only=True)
    lastName = serializers.CharField(source="user.last_name", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    mobile = serializers.CharField(source="user.mobile", read_only=True)
    admissionNumber = serializers.SerializerMethodField()
    displayAdmissionNumber = serializers.SerializerMethodField()
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
            "displayAdmissionNumber",
            "gender",
            "date_of_birth",
            "address",
            "admission_date",
            "school",
            "schoolName",
            "classSection",
            "className",
        ]

    def get_admissionNumber(self, obj):
        code = obj.school.code if obj.school else ""
        val = obj.admission_number or ""
        prefix = f"{code}-"
        if code and val.startswith(prefix):
            return val[len(prefix):]
        return val

    def get_displayAdmissionNumber(self, obj):
        return self.get_admissionNumber(obj)

    def get_className(self, obj):
        c = obj.class_section
        return f"{c.name}-{c.section}" if c else None


class RegisterSerializer(serializers.Serializer):
    role = serializers.CharField(required=False, default="parent")
    username = serializers.CharField(required=False, allow_blank=True, default="")
    password = serializers.CharField(required=True, write_only=True)
    firstName = serializers.CharField(required=False, allow_blank=True, default="")
    lastName = serializers.CharField(required=False, allow_blank=True, default="")
    name = serializers.CharField(required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    mobile = serializers.CharField(required=False, allow_blank=True, default="")
    schoolId = serializers.IntegerField(required=False, allow_null=True)
    instituteName = serializers.CharField(required=False, allow_blank=True, default="")
    designation = serializers.CharField(required=False, allow_blank=True, default="")
    admissionNumber = serializers.CharField(required=False, allow_blank=True, default="")
    employeeId = serializers.CharField(required=False, allow_blank=True, default="")
    gender = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        role_raw = attrs.get("role", "parent")
        role = role_raw.lower().strip() if role_raw else "parent"
        attrs["role"] = role

        institute_name = attrs.get("instituteName", "").strip()
        attrs["instituteName"] = institute_name

        if role == "admin":
            if not institute_name:
                raise serializers.ValidationError({"role": ["This role cannot be registered publicly"]})
        elif role not in ("student", "parent", "teacher"):
            raise serializers.ValidationError({"role": ["This role cannot be registered publicly"]})

        # Name handling (split full name into first and last if needed)
        name = attrs.get("name", "").strip()
        if name and not attrs.get("firstName"):
            parts = name.split(None, 1)
            attrs["firstName"] = parts[0]
            if len(parts) > 1:
                attrs["lastName"] = parts[1]

        username = attrs.get("username", "").strip()
        if username and re.match(r"^\d{10}$", username):
            raise serializers.ValidationError({"username": ["10-digit numeric usernames are reserved for mobile logins."]})

        if not username:
            email_val = attrs.get("email", "").strip()
            mobile_val = attrs.get("mobile", "").strip()
            if email_val:
                candidate = email_val.split("@")[0].lower()
            elif mobile_val:
                candidate = f"user_{mobile_val[-4:]}"
            elif name:
                candidate = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
            else:
                candidate = ""

            if not candidate:
                raise serializers.ValidationError({"username": ["This field is required."]})

            # Ensure uniqueness
            import random
            unique_username = candidate
            while User.objects.filter(username__iexact=unique_username).exists():
                unique_username = f"{candidate}_{random.randint(1000, 9999)}"
            username = unique_username

        attrs["username"] = username
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
        mobile = attrs.get("mobile", "").strip()
        attrs["mobile"] = mobile

        if (email and User.objects.filter(email__iexact=email).exists()) or (
            mobile and User.objects.filter(mobile=mobile).exists()
        ):
            raise serializers.ValidationError(
                {"detail": "An account with this email or mobile already exists. Please sign in or use password recovery."}
            )

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
            school = attrs.get("_school")
            internal_adm = f"{school.code}-{adm}" if school else adm
            from django.db.models import Q
            if Student.objects.filter(school=school).filter(
                Q(admission_number__iexact=internal_adm) | Q(admission_number__iexact=adm)
            ).exists():
                raise serializers.ValidationError({"admissionNumber": ["A student with that admission number already exists in this school."]})

        if role == "teacher":
            emp = attrs.get("employeeId", "").strip()
            attrs["employeeId"] = emp
            if not emp:
                raise serializers.ValidationError({"employeeId": ["This field is required."]})
            school = attrs.get("_school")
            internal_emp = f"{school.code}-{emp}" if school else emp
            from django.db.models import Q
            if Teacher.objects.filter(school=school).filter(
                Q(employee_id__iexact=internal_emp) | Q(employee_id__iexact=emp)
            ).exists():
                raise serializers.ValidationError({"employeeId": ["A teacher with that employee ID already exists in this school."]})

        return attrs

    def create(self, validated_data):
        import re
        from credentials.models import UserSecurity
        with transaction.atomic():
            user = User(
                username=validated_data["username"],
                email=validated_data.get("email", ""),
                mobile=validated_data.get("mobile", ""),
                first_name=validated_data.get("firstName", ""),
                last_name=validated_data.get("lastName", ""),
                role=validated_data["role"],
                is_staff=(validated_data["role"] == "admin"),
                is_superuser=False,
                is_active=True,
            )
            user.set_password(validated_data["password"])
            user.save()
            UserSecurity.objects.get_or_create(user=user, defaults={"created_via": "register"})

            if user.role == "student":
                adm = validated_data["admissionNumber"]
                school = validated_data["_school"]
                internal_adm = f"{school.code}-{adm}"
                Student.objects.create(
                    user=user,
                    school=school,
                    admission_number=internal_adm,
                    gender=validated_data.get("gender", ""),
                )
            elif user.role == "teacher":
                emp = validated_data["employeeId"]
                school = validated_data["_school"]
                internal_emp = f"{school.code}-{emp}"
                Teacher.objects.create(
                    user=user,
                    school=school,
                    employee_id=internal_emp,
                )
            elif user.role == "admin" and validated_data.get("instituteName"):
                clean_name = re.sub(r'[^A-Z0-9]', '', validated_data["instituteName"].upper())[:6] or "INST"
                base_code = f"{clean_name}-09"
                code = base_code
                counter = 1
                while School.objects.filter(code=code).exists():
                    code = f"{base_code}-{counter}"
                    counter += 1

                School.objects.create(
                    name=validated_data["instituteName"],
                    code=code,
                    address="Indore, Madhya Pradesh",
                    city="Indore",
                    phone=validated_data.get("mobile", ""),
                    email=validated_data.get("email", ""),
                    principal=user,
                )
            return user

