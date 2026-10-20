from django.contrib import admin
from .models import Topic, Unit


class TopicInline(admin.TabularInline):
    model = Topic
    extra = 1


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("subject", "unit_number", "title", "created_at")
    list_filter = ("subject__school", "subject")
    search_fields = ("title", "subject__name")
    inlines = [TopicInline]


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("unit", "topic_number", "title", "status", "completed_at")
    list_filter = ("status", "unit__subject__school")
    search_fields = ("title", "unit__title", "unit__subject__name")
