import re
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from audit.services import log_action
from .models import Guardian, StudentGuardian


def normalize_mobile(val):
    """
    Extract digits only and keep the last 10 digits.
    """
    if not val:
        return ""
    digits = re.sub(r"\D", "", str(val))
    return digits[-10:] if len(digits) >= 10 else digits


def add_student_guardian(student, full_name, mobile, relation="guardian", is_primary=False, email="", actor=None, request=None):
    """
    Principal adds a guardian to a student.
    Reuses existing Guardian row for (school, normalized_mobile) or creates a new one.
    Links via StudentGuardian.
    """
    norm_mobile = normalize_mobile(mobile)
    if len(norm_mobile) < 10:
        raise ValidationError({"mobile": ["Please provide a valid 10-digit mobile number."]})

    with transaction.atomic():
        # Find by school and matching normalized mobile
        school = student.school
        existing_guardian = None
        for g in Guardian.objects.filter(school=school):
            if normalize_mobile(g.mobile) == norm_mobile:
                existing_guardian = g
                break

        if not existing_guardian:
            existing_guardian = Guardian.objects.create(
                school=school,
                full_name=full_name.strip(),
                mobile=norm_mobile,
                email=email.strip() if email else "",
                link_status="unlinked",
            )
        else:
            # Update name/email if empty
            if not existing_guardian.full_name and full_name:
                existing_guardian.full_name = full_name.strip()
                existing_guardian.save(update_fields=["full_name"])

        # Check if already linked
        sg, created = StudentGuardian.objects.get_or_create(
            student=student,
            guardian=existing_guardian,
            defaults={"relation": relation, "is_primary": is_primary},
        )
        if not created:
            # Update relation/is_primary
            sg.relation = relation
            if is_primary and not sg.is_primary:
                # Clear other primaries for this student
                StudentGuardian.objects.filter(student=student, is_primary=True).exclude(id=sg.id).update(is_primary=False)
                sg.is_primary = True
            sg.save()
        elif is_primary:
            StudentGuardian.objects.filter(student=student, is_primary=True).exclude(id=sg.id).update(is_primary=False)

        log_action(
            actor=actor,
            school=school,
            action="guardian.add",
            obj=sg,
            changes={
                "studentId": student.id,
                "guardianId": existing_guardian.id,
                "relation": relation,
                "isPrimary": is_primary,
            },
            request=request,
        )

        return sg


def remove_student_guardian(student, guardian_id, actor=None, request=None):
    """
    Removes the StudentGuardian link. If the Guardian has no other students in this school,
    it remains or can be retained in unlinked state.
    """
    with transaction.atomic():
        sg = StudentGuardian.objects.filter(student=student, guardian_id=guardian_id).first()
        if not sg:
            return False

        school = student.school
        log_action(
            actor=actor,
            school=school,
            action="guardian.remove",
            obj=sg,
            changes={"studentId": student.id, "guardianId": guardian_id},
            request=request,
        )
        sg.delete()
        return True


def claim_guardians_for_parent(user, request=None):
    """
    Reads request.user.mobile only.
    Compares normalized user.mobile with normalized Guardian.mobile.
    Marks matching unlinked guardians as pending with requested_user = user.
    """
    user_mobile = getattr(user, "mobile", "")
    norm_mobile = normalize_mobile(user_mobile)
    if not norm_mobile or len(norm_mobile) < 10:
        raise ValidationError("Add your mobile number to your account first.")

    matched_schools = set()
    pending_count = 0

    with transaction.atomic():
        all_guardians = Guardian.objects.select_related("school").filter(link_status="unlinked")
        for g in all_guardians:
            if normalize_mobile(g.mobile) == norm_mobile:
                # Check if user is already linked in this school
                if Guardian.objects.filter(school=g.school, user=user).exists():
                    continue
                g.requested_user = user
                g.link_status = "pending"
                g.save(update_fields=["requested_user", "link_status"])
                matched_schools.add(g.school.name)
                pending_count += 1

                log_action(
                    actor=user,
                    school=g.school,
                    action="guardian.claim",
                    obj=g,
                    changes={"guardianId": g.id, "requestedUser": user.username},
                    request=request,
                )

    return {
        "pendingCount": pending_count,
        "matchedSchools": sorted(list(matched_schools)),
    }


def approve_guardian_link(guardian, principal, request=None):
    """
    Principal approves a pending claim.
    """
    if guardian.link_status != "pending" or not guardian.requested_user:
        raise ValidationError("Guardian has no pending claim request.")

    # Check if this user is already linked to another guardian in this school
    req_user = guardian.requested_user
    if Guardian.objects.filter(school=guardian.school, user=req_user).exclude(id=guardian.id).exists():
        raise ValidationError("This user is already linked as a guardian for another record in this school.")

    with transaction.atomic():
        guardian.user = req_user
        guardian.link_status = "approved"
        guardian.decided_by = principal
        guardian.decided_at = timezone.now()
        guardian.save(update_fields=["user", "link_status", "decided_by", "decided_at"])

        log_action(
            actor=principal,
            school=guardian.school,
            action="guardian.approve",
            obj=guardian,
            changes={"guardianId": guardian.id, "approvedUserId": req_user.id},
            request=request,
        )

    return guardian


def reject_guardian_link(guardian, principal, request=None):
    """
    Principal rejects a pending claim. Resets to unlinked.
    """
    if guardian.link_status != "pending":
        raise ValidationError("Guardian has no pending claim request.")

    with transaction.atomic():
        prev_user_id = guardian.requested_user_id
        guardian.requested_user = None
        guardian.link_status = "unlinked"
        guardian.decided_by = principal
        guardian.decided_at = timezone.now()
        guardian.save(update_fields=["requested_user", "link_status", "decided_by", "decided_at"])

        log_action(
            actor=principal,
            school=guardian.school,
            action="guardian.reject",
            obj=guardian,
            changes={"guardianId": guardian.id, "rejectedUserId": prev_user_id},
            request=request,
        )

    return guardian
