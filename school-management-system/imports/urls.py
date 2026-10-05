from django.urls import path

from .views import (
    import_excel,
    confirm_import,
)


urlpatterns = [

    path(
        "excel/",
        import_excel,
        name="import_excel"
    ),

    path(
        "excel/confirm/",
        confirm_import,
        name="confirm_import"
    ),
]