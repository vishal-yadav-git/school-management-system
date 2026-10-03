from django.db import models
from django.conf import settings
from schools.models import School


class Teacher(models.Model):

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
        max_length=200,
        blank=True
    )

    joining_date = models.DateField(
        null=True,
        blank=True
    )

    designation = models.CharField(
        max_length=100,
        default='Teacher'
    )

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.school.name}"


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

    address = models.TextField(
        blank=True
    )

    admission_date = models.DateField(
        auto_now_add=True
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