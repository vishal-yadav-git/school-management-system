from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from accounts.models import User
from schools.models import School

from .models import Teacher, Student
from .forms import TeacherForm

from .models import Teacher, Student, SchoolClass
from .forms import TeacherForm, SchoolClassForm

from .forms import (TeacherForm, SchoolClassForm, StudentForm,)


from .forms import (
    TeacherForm,
    SchoolClassForm,
    StudentForm,
)
# =========================================================
# TEACHER STUDENTS
# =========================================================

@login_required
def teacher_students(request):

    user = request.user

    if user.role != 'teacher':
        return redirect('dashboard')

    try:
        teacher = user.teacher_profile
    except Teacher.DoesNotExist:
        return redirect('dashboard')

    classes = teacher.class_teacher_for.all()

    students = Student.objects.filter(
        class_section__in=classes,
        school=teacher.school
    ).select_related(
        'user',
        'class_section'
    )

    return render(
        request,
        'teacher_students.html',
        {
            'teacher': teacher,
            'students': students
        }
    )


# =========================================================
# TEACHER LIST
# =========================================================

@login_required
def teacher_list(request):

    # Main Admin
    if request.user.is_superuser:

        teachers = Teacher.objects.all().select_related(
            'user',
            'school'
        )

    # Principal
    elif request.user.role == 'principal':

        try:
            school = request.user.principal_school
        except School.DoesNotExist:
            return redirect('dashboard')

        teachers = Teacher.objects.filter(
            school=school
        ).select_related(
            'user',
            'school'
        )

    else:

        return redirect('dashboard')

    return render(
        request,
        'academics/teacher_list.html',
        {
            'teachers': teachers
        }
    )


# =========================================================
# ADD TEACHER
# =========================================================

@login_required
def teacher_create(request):

    # Principal -> own school automatically
    if request.user.role == 'principal':

        try:
            school = request.user.principal_school
        except School.DoesNotExist:
            return redirect('dashboard')

        if school is None:
            return redirect('dashboard')

    # Main Admin -> school supplied through URL
    elif request.user.is_superuser:

        school_id = request.GET.get('school')

        if not school_id:
            return redirect('school_list')

        school = get_object_or_404(
            School,
            id=school_id
        )

    else:
        return redirect('dashboard')

    if request.method == 'POST':

        form = TeacherForm(request.POST)

        if form.is_valid():

            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                email=form.cleaned_data['email'],
                mobile=form.cleaned_data['mobile'],
                role='teacher'
            )

            Teacher.objects.create(
                user=user,
                school=school,

                employee_id=form.cleaned_data[
                    'employee_id'
                ],

                qualification=form.cleaned_data[
                    'qualification'
                ],

                designation=form.cleaned_data[
                    'designation'
                ],

                department=form.cleaned_data[
                    'department'
                ],

                subject=form.cleaned_data[
                    'subject'
                ],

                experience=form.cleaned_data[
                    'experience'
                ] or 0,

                joining_date=form.cleaned_data[
                    'joining_date'
                ],

                date_of_birth=form.cleaned_data[
                    'date_of_birth'
                ],

                gender=form.cleaned_data[
                    'gender'
                ],

                address=form.cleaned_data[
                    'address'
                ],

                emergency_contact=form.cleaned_data[
                    'emergency_contact'
                ]
            )

            return redirect('teacher_list')

    else:
        form = TeacherForm()

    return render(
        request,
        'academics/teacher_form.html',
        {
            'form': form,
            'school': school,
            'title': 'Add Teacher'
        }
    )

# =========================================================
# DELETE TEACHER
# =========================================================

@login_required
def teacher_delete(request, pk):

    # Principal
    if request.user.role == 'principal':

        try:
            school = request.user.principal_school
        except School.DoesNotExist:
            return redirect('dashboard')

        teacher = get_object_or_404(
            Teacher,
            pk=pk,
            school=school
        )

    # Main Admin
    elif request.user.is_superuser:

        teacher = get_object_or_404(
            Teacher,
            pk=pk
        )

    else:

        return redirect('dashboard')

    if request.method == 'POST':

        user = teacher.user

        teacher.delete()

        user.delete()

        return redirect('teacher_list')

    return render(
        request,
        'academics/teacher_confirm_delete.html',
        {
            'teacher': teacher
        }
    )


@login_required
def class_list(request):

    if request.user.is_superuser:

        classes = SchoolClass.objects.all().select_related(
            'school',
            'class_teacher',
            'class_teacher__user'
        )

    elif request.user.role == 'principal':

        try:
            school = request.user.principal_school
        except School.DoesNotExist:
            return redirect('dashboard')

        classes = SchoolClass.objects.filter(
            school=school
        ).select_related(
            'school',
            'class_teacher',
            'class_teacher__user'
        )

    else:

        return redirect('dashboard')

    return render(
        request,
        'academics/class_list.html',
        {
            'classes': classes
        }
    )



@login_required
def class_create(request):

    if request.user.role == 'principal':

        try:
            school = request.user.principal_school
        except School.DoesNotExist:
            return redirect('dashboard')

        if school is None:
            return redirect('dashboard')

    elif request.user.is_superuser:

        school_id = request.GET.get('school')

        if not school_id:
            return redirect('school_list')

        school = get_object_or_404(
            School,
            id=school_id
        )

    else:

        return redirect('dashboard')

    if request.method == 'POST':

        form = SchoolClassForm(
            request.POST,
            school=school
        )

        if form.is_valid():

            school_class = form.save(
                commit=False
            )

            school_class.school = school

            school_class.save()

            return redirect('class_list')

    else:

        form = SchoolClassForm(
            school=school
        )

    return render(
        request,
        'academics/class_form.html',
        {
            'form': form,
            'school': school,
            'title': 'Add Class'
        }
    )



@login_required
def class_delete(request, pk):

    if request.user.role == 'principal':

        try:
            school = request.user.principal_school
        except School.DoesNotExist:
            return redirect('dashboard')

        school_class = get_object_or_404(
            SchoolClass,
            pk=pk,
            school=school
        )

    elif request.user.is_superuser:

        school_class = get_object_or_404(
            SchoolClass,
            pk=pk
        )

    else:

        return redirect('dashboard')

    if request.method == 'POST':

        school_class.delete()

        return redirect('class_list')

    return render(
        request,
        'academics/class_confirm_delete.html',
        {
            'school_class': school_class
        }
    )


@login_required
def student_list(request):

    if request.user.is_superuser:

        students = Student.objects.all().select_related(
            'user',
            'school',
            'class_section'
        )

    elif request.user.role == 'principal':

        try:
            school = request.user.principal_school
        except School.DoesNotExist:
            return redirect('dashboard')

        students = Student.objects.filter(
            school=school
        ).select_related(
            'user',
            'school',
            'class_section'
        )

    else:

        return redirect('dashboard')

    return render(
        request,
        'academics/student_list.html',
        {
            'students': students
        }
    )


@login_required
def student_create(request):

    if request.user.role == 'principal':

        try:
            school = request.user.principal_school
        except School.DoesNotExist:
            return redirect('dashboard')

        if school is None:
            return redirect('dashboard')

    elif request.user.is_superuser:

        school_id = request.GET.get('school')

        if not school_id:
            return redirect('school_list')

        school = get_object_or_404(
            School,
            id=school_id
        )

    else:

        return redirect('dashboard')

    if request.method == 'POST':

        form = StudentForm(
            request.POST,
            school=school
        )

        if form.is_valid():

            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                email=form.cleaned_data['email'],
                role='student'
            )

            Student.objects.create(
                user=user,
                school=school,
                class_section=form.cleaned_data[
                    'class_section'
                ],
                admission_number=form.cleaned_data[
                    'admission_number'
                ],
                father_name=form.cleaned_data[
                    'father_name'
                ],
                mother_name=form.cleaned_data[
                    'mother_name'
                ],
                mobile_no=form.cleaned_data[
                    'mobile_no'
                ],
                alternate_mobile=form.cleaned_data[
                    'alternate_mobile'
                ],
                date_of_birth=form.cleaned_data[
                    'date_of_birth'
                ],
                gender=form.cleaned_data[
                    'gender'
                ],
                email=form.cleaned_data[
                    'email'
                ],
                address=form.cleaned_data[
                    'address'
                ],
                caste=form.cleaned_data[
                    'caste'
                ],
                fees=form.cleaned_data[
                    'fees'
                ] or 0,
                transport=form.cleaned_data[
                    'transport'
                ],
                hostel=form.cleaned_data[
                    'hostel'
                ],
                subject=form.cleaned_data[
                    'subject'
                ],
                admission_date=form.cleaned_data[
                    'admission_date'
                ]
            )

            return redirect('student_list')

    else:

        form = StudentForm(
            school=school
        )

    return render(
        request,
        'academics/student_form.html',
        {
            'form': form,
            'school': school,
            'title': 'Add Student'
        }
    )


@login_required
def student_delete(request, pk):

    if request.user.role == 'principal':

        try:
            school = request.user.principal_school
        except School.DoesNotExist:
            return redirect('dashboard')

        student = get_object_or_404(
            Student,
            pk=pk,
            school=school
        )

    elif request.user.is_superuser:

        student = get_object_or_404(
            Student,
            pk=pk
        )

    else:

        return redirect('dashboard')

    if request.method == 'POST':

        user = student.user

        student.delete()

        user.delete()

        return redirect('student_list')

    return render(
        request,
        'academics/student_confirm_delete.html',
        {
            'student': student
        }
    )