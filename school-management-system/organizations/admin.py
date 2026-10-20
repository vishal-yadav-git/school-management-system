from django.contrib import admin
from .models import Organization, SchoolOrganization, OrganizationMember, EmailVerificationToken


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "owner", "created_at"]
    search_fields = ["name", "code", "owner__username"]


@admin.register(SchoolOrganization)
class SchoolOrganizationAdmin(admin.ModelAdmin):
    list_display = ["school", "organization", "status", "is_main_campus", "created_at"]
    list_filter = ["status", "is_main_campus", "organization"]
    search_fields = ["school__name", "organization__name"]


@admin.register(OrganizationMember)
class OrganizationMemberAdmin(admin.ModelAdmin):
    list_display = ["organization", "user", "role", "created_at"]
    list_filter = ["role", "organization"]
    search_fields = ["user__username", "organization__name"]


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "expires_at", "is_used", "created_at"]
    list_filter = ["is_used"]
    search_fields = ["user__username"]
