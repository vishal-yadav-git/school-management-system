from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from .models import Student


@login_required
def teacher_students(request):

    user = request.user

    if user.role != 'teacher':
        return redirect('dashboard')

    try:
        teacher = user.teacher_profile
    except Exception:
        return redirect('dashboard')

    classes = teacher.class_teacher_for.all()

    students = Student.objects.filter(
        class_section__in=classes,
        school=teacher.school
    )

    return render(
        request,
        'teacher_students.html',
        {
            'teacher': teacher,
            'students': students,
        }
    )