import hashlib
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from audit.services import log_action
from schools.models import School

from .models import EmailVerificationToken, Organization, OrganizationMember, SchoolOrganization


def generate_unique_code(name, model_cls, prefix="", max_len=12):
    clean = re.sub(r"[^A-Z0-9]", "", name.upper())[:6] or prefix or "ORG"
    base = f"{clean}-09"
    code = base
    counter = 1
    while model_cls.objects.filter(code=code).exists():
        code = f"{base[:max_len-4]}-{counter}"
        counter += 1
    return code


def get_active_school_for_user(request):
    """
    Resolves and returns the active school for the requesting user.
    Re-validates organization membership on EVERY request.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    # Superuser can access any school, via query param, session, or default
    if user.is_superuser:
        school_id = request.query_params.get("school") or request.session.get("active_school_id")
        if school_id:
            try:
                return School.objects.get(pk=school_id)
            except (School.DoesNotExist, ValueError):
                pass
        return School.objects.order_by("id").first()

    # Org owner/admin: multi-campus switching with on-every-request membership check
    if getattr(user, "role", "") == "admin":
        valid_memberships = OrganizationMember.objects.filter(
            user=user,
            role__in=["owner", "admin"],
        ).values_list("organization_id", flat=True)

        if valid_memberships:
            target_id = request.session.get("active_school_id") or request.query_params.get("school")
            if target_id:
                so = SchoolOrganization.objects.filter(
                    school_id=target_id,
                    organization_id__in=valid_memberships,
                ).select_related("school").first()
                if so:
                    return so.school

            # Default to main campus or first campus of their organization
            first_so = SchoolOrganization.objects.filter(
                organization_id__in=valid_memberships,
            ).select_related("school").order_by("-is_main_campus", "id").first()
            if first_so:
                request.session["active_school_id"] = first_so.school.id
                return first_so.school

    # Campus principal: bound directly to their principal_school
    principal_school = getattr(user, "principal_school", None)
    if principal_school:
        return principal_school

    # Teachers and Students: bound through profile
    teacher = getattr(user, "teacher_profile", None)
    if teacher and teacher.school:
        return teacher.school

    student = getattr(user, "student_profile", None)
    if student and student.school:
        return student.school

    return None


def switch_active_campus(user, target_school_id, request=None):
    """
    Switches active campus for an organization owner/admin.
    Verifies that the target school belongs to an organization where user is owner/admin.
    """
    if user.is_superuser:
        try:
            school = School.objects.get(pk=target_school_id)
        except School.DoesNotExist:
            raise ValidationError("Target school does not exist.")
        if request:
            request.session["active_school_id"] = school.id
        return school

    so = SchoolOrganization.objects.filter(
        school_id=target_school_id,
        organization__members__user=user,
        organization__members__role__in=["owner", "admin"],
    ).select_related("school", "organization").first()

    if not so:
        raise PermissionDenied("Access denied: You are not an administrator of this campus.")

    if request:
        request.session["active_school_id"] = so.school.id

    # Log action in AuditLog
    log_action(
        actor=user,
        school=so.school,
        action="campus.switch",
        obj=so.school,
        changes={"switched_to_school_id": so.school.id, "school_name": so.school.name},
        request=request,
    )

    return so.school


def create_organization_with_campus(data):
    """
    Creates Organization + School + User + SchoolOrganization (pending) + EmailToken.
    Returns (user, organization, school, raw_token).
    """
    org_name = data.get("organizationName", "").strip()
    campus_name = data.get("campusName", "").strip() or f"{org_name} Main Campus"
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    mobile = data.get("mobile", "").strip()
    password = data.get("password", "")

    with transaction.atomic():
        user = User.objects.create_user(
            username=username,
            email=email,
            mobile=mobile,
            first_name=org_name,
            role="admin",
            is_staff=True,
        )
        user.set_password(password)
        user.save()

        from credentials.models import UserSecurity
        UserSecurity.objects.get_or_create(user=user, defaults={"created_via": "register"})

        org_code = generate_unique_code(org_name, Organization, prefix="ORG")
        organization = Organization.objects.create(
            name=org_name,
            code=org_code,
            owner=user,
        )

        campus_code = generate_unique_code(campus_name, School, prefix="SCH")
        school = School.objects.create(
            name=campus_name,
            code=campus_code,
            address="Indore, Madhya Pradesh",
            city="Indore",
            phone=mobile,
            email=email,
            principal=user,
        )

        SchoolOrganization.objects.create(
            school=school,
            organization=organization,
            status="pending",
            is_main_campus=True,
        )

        OrganizationMember.objects.create(
            organization=organization,
            user=user,
            role="owner",
        )

        # Generate single-use SHA-256 hashed verification token
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = timezone.now() + timedelta(hours=24)

        EmailVerificationToken.objects.create(
            user=user,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        # Send email (console in dev/test, SMTP in prod)
        verify_url = f"http://localhost:3000/verify-email?token={raw_token}"
        subject = f"Verify your institution: {org_name}"
        message = (
            f"Hello {user.username},\n\n"
            f"Thank you for registering {org_name} on IndoreEdu.\n"
            f"Please verify your email address by clicking the link below:\n\n"
            f"{verify_url}\n\n"
            f"This link expires in 24 hours.\n\n"
            f"Best regards,\nIndoreEdu Team"
        )
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@indoreedu.in"),
            recipient_list=[email],
            fail_silently=True,
        )

        return user, organization, school, raw_token


def verify_email_token(raw_token):
    """
    Hashes raw token, validates against DB, activates SchoolOrganization.
    """
    if not raw_token:
        raise ValidationError("Verification token is required.")

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    token = EmailVerificationToken.objects.filter(
        token_hash=token_hash,
        is_used=False,
        expires_at__gte=timezone.now(),
    ).select_related("user").first()

    if not token:
        raise ValidationError("Invalid or expired verification link.")

    with transaction.atomic():
        token.is_used = True
        token.save(update_fields=["is_used"])

        # Activate all campuses owned by this user
        SchoolOrganization.objects.filter(
            organization__owner=token.user,
        ).update(status="active")

        # Log action in AuditLog for each activated school
        for so in SchoolOrganization.objects.filter(organization__owner=token.user).select_related("school"):
            log_action(
                actor=token.user,
                school=so.school,
                action="organization.email_verified",
                obj=so.school,
                changes={"status": "active"},
            )

    return token.user
