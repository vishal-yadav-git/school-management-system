from django.urls import path

from .views import (
    school_list,
    school_create,
    school_update,
    school_delete,
    principal_list,
    principal_create,
    principal_delete,
)


urlpatterns = [

    path(
        '',
        school_list,
        name='school_list'
    ),

    path(
        'add/',
        school_create,
        name='school_create'
    ),

    path(
        'edit/<int:pk>/',
        school_update,
        name='school_update'
    ),

    path(
        'delete/<int:pk>/',
        school_delete,
        name='school_delete'
    ),

    path(
        'principals/',
        principal_list,
        name='principal_list'
    ),

    path(
        'principals/add/',
        principal_create,
        name='principal_create'
    ),

    path(
        'principals/delete/<int:pk>/',
        principal_delete,
        name='principal_delete'
    ),

]