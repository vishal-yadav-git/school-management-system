from django.db import models
from django.conf import settings
from schools.models import School


class Teacher(models.Model):

    GENDER_CHOICES = (
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='teacher_profile'
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='teachers'
    )

    employee_id = models.CharField(
        max_length=50,
        unique=True
    )

    qualification = models.CharField(
        max_length=200
    )

    designation = models.CharField(
        max_length=100,
        default='Teacher'
    )

    department = models.CharField(
        max_length=100,
        blank=True
    )

    subject = models.CharField(
        max_length=200,
        blank=True
    )

    experience = models.PositiveIntegerField(
        default=0,
        help_text='Experience in years'
    )

    joining_date = models.DateField(
        null=True,
        blank=True
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True
    )

    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        blank=True
    )

    address = models.TextField(
        blank=True
    )

    emergency_contact = models.CharField(
        max_length=20,
        blank=True
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        null=True,
        blank=True
    )

    def __str__(self):
        name = self.user.get_full_name() or self.user.username
        return f"{name} - {self.employee_id} - {self.school.name}"

class SchoolClass(models.Model):

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='classes'
    )

    name = models.CharField(
        max_length=50
    )

    section = models.CharField(
        max_length=10
    )

    class_teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='class_teacher_for'
    )

    def __str__(self):
        return f"{self.name} - {self.section} ({self.school.name})"


class Student(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_profile'
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='students'
    )

    class_section = models.ForeignKey(
        SchoolClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students'
    )

    admission_number = models.CharField(
        max_length=50,
        unique=True
    )

    # -------------------------
    # PARENT INFORMATION
    # -------------------------

    father_name = models.CharField(
        max_length=200,
        blank=True
    )

    mother_name = models.CharField(
        max_length=200,
        blank=True
    )

    # -------------------------
    # CONTACT INFORMATION
    # -------------------------

    mobile_no = models.CharField(
        max_length=20,
        blank=True
    )

    alternate_mobile = models.CharField(
        max_length=20,
        blank=True
    )

    email = models.EmailField(
        blank=True
    )

    address = models.TextField(
        blank=True
    )

    # -------------------------
    # PERSONAL INFORMATION
    # -------------------------

    date_of_birth = models.DateField(
        null=True,
        blank=True
    )

    gender = models.CharField(
        max_length=20,
        choices=[
            ('Male', 'Male'),
            ('Female', 'Female'),
            ('Other', 'Other'),
        ],
        blank=True
    )

    caste = models.CharField(
        max_length=100,
        blank=True
    )

    # -------------------------
    # ADMISSION INFORMATION
    # -------------------------

    admission_date = models.DateField(
        null=True,
        blank=True
    )

    # -------------------------
    # FEES
    # -------------------------

    fees = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # -------------------------
    # TRANSPORT / HOSTEL
    # -------------------------

    transport = models.CharField(
        max_length=100,
        blank=True
    )

    hostel = models.CharField(
        max_length=100,
        blank=True
    )

    # -------------------------
    # SUBJECT
    # -------------------------

    subject = models.CharField(
        max_length=200,
        blank=True
    )

    # -------------------------
    # TIMESTAMP
    # -------------------------

    created_at = models.DateTimeField(
    auto_now_add=True,
    null=True,
    blank=True
)

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.admission_number}"


class Subject(models.Model):

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='subjects'
    )

    name = models.CharField(
        max_length=100
    )

    code = models.CharField(
        max_length=30
    )

    def __str__(self):
        return f"{self.name} - {self.school.name}"