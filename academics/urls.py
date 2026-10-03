from django.urls import path

from .views import teacher_students


urlpatterns = [

    path(
        'teacher/students/',
        teacher_students,
        name='teacher_students'
    ),

]