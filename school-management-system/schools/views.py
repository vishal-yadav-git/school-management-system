from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from .models import School
from .forms import SchoolForm, PrincipalForm
from accounts.models import User


# =========================================================
# SCHOOL CRUD
# =========================================================

@login_required
def school_list(request):

    if not request.user.is_superuser:
        return redirect('dashboard')

    schools = School.objects.all().order_by('-created_at')

    return render(
        request,
        'schools/school_list.html',
        {
            'schools': schools
        }
    )


@login_required
def school_create(request):

    if not request.user.is_superuser:
        return redirect('dashboard')

    if request.method == 'POST':

        form = SchoolForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect('school_list')

    else:
        form = SchoolForm()

    return render(
        request,
        'schools/school_form.html',
        {
            'form': form,
            'title': 'Add School'
        }
    )


@login_required
def school_update(request, pk):

    if not request.user.is_superuser:
        return redirect('dashboard')

    school = get_object_or_404(School, pk=pk)

    if request.method == 'POST':

        form = SchoolForm(
            request.POST,
            instance=school
        )

        if form.is_valid():
            form.save()
            return redirect('school_list')

    else:
        form = SchoolForm(
            instance=school
        )

    return render(
        request,
        'schools/school_form.html',
        {
            'form': form,
            'title': 'Edit School'
        }
    )


@login_required
def school_delete(request, pk):

    if not request.user.is_superuser:
        return redirect('dashboard')

    school = get_object_or_404(
        School,
        pk=pk
    )

    if request.method == 'POST':

        school.delete()

        return redirect('school_list')

    return render(
        request,
        'schools/school_confirm_delete.html',
        {
            'school': school
        }
    )


# =========================================================
# PRINCIPAL MANAGEMENT
# =========================================================

@login_required
def principal_list(request):

    if not request.user.is_superuser:
        return redirect('dashboard')

    principals = User.objects.filter(
        role='principal'
    ).select_related(
        'principal_school'
    )

    return render(
        request,
        'schools/principal_list.html',
        {
            'principals': principals
        }
    )


@login_required
def principal_create(request):

    if not request.user.is_superuser:
        return redirect('dashboard')

    if request.method == 'POST':

        form = PrincipalForm(request.POST)

        if form.is_valid():

            user = form.save(commit=False)

            user.role = 'principal'

            user.set_password(
                form.cleaned_data['password']
            )

            user.save()

            school = form.cleaned_data['school']

            school.principal = user

            school.save()

            return redirect('principal_list')

    else:

        form = PrincipalForm()

    return render(
        request,
        'schools/principal_form.html',
        {
            'form': form,
            'title': 'Add Principal'
        }
    )


@login_required
def principal_delete(request, pk):

    if not request.user.is_superuser:
        return redirect('dashboard')

    principal = get_object_or_404(
        User,
        pk=pk,
        role='principal'
    )

    if request.method == 'POST':

        School.objects.filter(
            principal=principal
        ).update(
            principal=None
        )

        principal.delete()

        return redirect('principal_list')

    return render(
        request,
        'schools/principal_confirm_delete.html',
        {
            'principal': principal
        }
    )