from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from schools.models import School
from academics.models import Teacher, Student, SchoolClass, Subject
from accounts.models import User


def home(request):
    return render(request, 'home.html')


@login_required
def dashboard(request):

    user = request.user

    if user.is_superuser:
        return redirect('admin_dashboard')

    if user.role == 'principal':
        return redirect('principal_dashboard')

    if user.role == 'teacher':
        return redirect('teacher_dashboard')

    if user.role == 'student':
        return redirect('student_dashboard')

    if user.role == 'parent':
        return redirect('parent_dashboard')

    return redirect('home')


@login_required
def admin_dashboard(request):

    if not request.user.is_superuser:
        return redirect('dashboard')

    context = {
        'total_schools': School.objects.count(),
        'total_principals': User.objects.filter(
            role='principal'
        ).count(),

        'total_teachers': Teacher.objects.count(),

        'total_students': Student.objects.count(),

        'total_classes': SchoolClass.objects.count(),

        'total_subjects': Subject.objects.count(),
    }

    return render(
        request,
        'admin_dashboard.html',
        context
    )


@login_required
def principal_dashboard(request):

    if request.user.role != 'principal':
        return redirect('dashboard')

    try:
        school = request.user.principal_school
    except Exception:
        school = None

    return render(
        request,
        'principal_dashboard.html',
        {
            'school': school
        }
    )


@login_required
def teacher_dashboard(request):

    if request.user.role != 'teacher':
        return redirect('dashboard')

    return render(
        request,
        'teacher_dashboard.html'
    )


@login_required
def student_dashboard(request):

    if request.user.role != 'student':
        return redirect('dashboard')

    return render(
        request,
        'student_dashboard.html'
    )


@login_required
def parent_dashboard(request):

    if request.user.role != 'parent':
        return redirect('dashboard')

    return render(
        request,
        'parent_dashboard.html'
    )