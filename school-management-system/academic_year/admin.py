from django.contrib import admin
from .models import AcademicYear


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "start_date", "end_date", "is_current")
    list_filter = ("school", "is_current")
    search_fields = ("name", "school__name")
