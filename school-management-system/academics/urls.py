from django.urls import path

from .views import (
    teacher_students,
    teacher_list,
    teacher_create,
    teacher_delete,
    class_list,
    class_create,
    class_delete,
    student_list,
    student_create,
    student_delete,
)


urlpatterns = [

    path(
        'teacher/students/',
        teacher_students,
        name='teacher_students'
    ),

    path(
        'teachers/',
        teacher_list,
        name='teacher_list'
    ),

    path(
        'teachers/add/',
        teacher_create,
        name='teacher_create'
    ),

    path(
        'teachers/delete/<int:pk>/',
        teacher_delete,
        name='teacher_delete'
    ),

    path(
        'classes/',
        class_list,
        name='class_list'
    ),

    path(
        'classes/add/',
        class_create,
        name='class_create'
    ),

    path(
        'classes/delete/<int:pk>/',
        class_delete,
        name='class_delete'
    ),
    path(
    'students/',
    student_list,
    name='student_list'
),

path(
    'students/add/',
    student_create,
    name='student_create'
),

path(
    'students/delete/<int:pk>/',
    student_delete,
    name='student_delete'
),

]