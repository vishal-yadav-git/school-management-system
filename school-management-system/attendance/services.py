from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from academic_year.models import AcademicYear
from audit.services import log_action
from .models import AttendanceRecord, AttendanceSession


def upsert_attendance_session(school_class, date, records_data, actor, request=None):
    """
    Atomic idempotent upsert of AttendanceSession and AttendanceRecord rows.
    """
    today = timezone.localdate()
    if date > today:
        raise ValidationError({"date": ["Cannot mark attendance for future dates."]})

    school = school_class.school
    ay = AcademicYear.objects.filter(school=school, is_current=True).first()
    if not ay:
        raise ValidationError({"academic_year": ["No active academic year found for this school."]})

    if date < ay.start_date or date > ay.end_date:
        raise ValidationError({"date": ["Attendance date must be within the current academic year."]})

    # Teacher permission checks
    is_principal_or_su = actor.is_superuser or getattr(actor, "role", "") in ("principal", "admin")
    has_backdate_perm = False
    if not is_principal_or_su and hasattr(actor, "teacher_profile"):
        try:
            from teacher_assignments.services import has_teacher_permission
            has_backdate_perm = has_teacher_permission(actor.teacher_profile, "attendance_backdate")
        except Exception:
            has_backdate_perm = False

    if not is_principal_or_su:
        # Teacher must be class_teacher
        if not school_class.class_teacher or school_class.class_teacher.user_id != actor.id:
            raise PermissionDenied("Only the designated class teacher or principal can take attendance for this class.")
        if date != today and not has_backdate_perm:
            raise PermissionDenied("Teachers can only submit attendance for today.")

    # Validate students match exactly the class roster
    class_student_ids = set(school_class.students.values_list("id", flat=True))
    submitted_student_ids = {r["studentId"] for r in records_data}

    if class_student_ids != submitted_student_ids:
        raise ValidationError({"records": ["Attendance records must contain all and only enrolled students of this class."]})

    with transaction.atomic():
        session, created = AttendanceSession.objects.get_or_create(
            school_class=school_class,
            date=date,
            defaults={
                "school": school,
                "academic_year": ay,
                "taken_by": actor,
            },
        )

        before_state = {}
        if not created:
            # Editing an existing session
            if date != today and not is_principal_or_su and not has_backdate_perm:
                raise PermissionDenied("Only the principal can edit attendance for past dates.")
            before_state = {r.student_id: r.status for r in session.records.all()}
            session.taken_by = actor
            session.save(update_fields=["taken_by", "updated_at"])

        after_state = {}
        for r_data in records_data:
            s_id = r_data["studentId"]
            status_val = r_data.get("status", "present")
            remark_val = r_data.get("remark", "")
            rec, _ = AttendanceRecord.objects.update_or_create(
                session=session,
                student_id=s_id,
                defaults={"status": status_val, "remark": remark_val},
            )
            after_state[s_id] = status_val

        # Log action
        action_name = "attendance.create" if created else "attendance.update"
        changes = {
            "classId": school_class.id,
            "className": f"{school_class.name}-{school_class.section}",
            "date": str(date),
            "recordCount": len(records_data),
        }
        if not created:
            changes["before"] = before_state
            changes["after"] = after_state

        log_action(
            actor=actor,
            school=school,
            action=action_name,
            obj=session,
            changes=changes,
            request=request,
        )

    return session


def get_class_attendance_roster(school_class, date=None):
    """
    Returns the attendance roster for a class on a given date.
    If not taken yet, defaults all enrolled students to 'present'.
    """
    if not date:
        date = timezone.localdate()

    session = AttendanceSession.objects.filter(school_class=school_class, date=date).first()
    exists = session is not None

    record_map = {}
    if session:
        for r in session.records.all():
            record_map[r.student_id] = {"status": r.status, "remark": r.remark}

    students_data = []
    school_code = getattr(school_class.school, "code", "")
    prefix = f"{school_code}-" if school_code else ""
    for s in school_class.students.select_related("user").order_by("admission_number"):
        rec = record_map.get(s.id, {"status": "present", "remark": ""})
        adm_no = s.admission_number or ""
        display_adm = adm_no[len(prefix):] if prefix and adm_no.startswith(prefix) else adm_no
        students_data.append({
            "studentId": s.id,
            "name": s.user.get_full_name() or s.user.username,
            "admissionNumber": adm_no,
            "displayAdmissionNumber": display_adm,
            "status": rec["status"],
            "remark": rec["remark"],
        })

    return {
        "classId": school_class.id,
        "className": f"{school_class.name}-{school_class.section}",
        "date": str(date),
        "exists": exists,
        "students": students_data,
    }


def get_school_attendance_summary(school, date=None):
    """
    Calculates class-wise and school-wide attendance metrics for a given date.
    """
    if not date:
        date = timezone.localdate()

    classes = school.classes.prefetch_related("students", "attendance_sessions__records").all()

    class_summaries = []
    total_school_students = 0
    total_school_present = 0
    total_school_absent = 0
    total_school_late = 0
    total_school_leave = 0

    for c in classes:
        session = c.attendance_sessions.filter(date=date).first()
        c_students = c.students.count()
        if c_students == 0:
            continue

        p_count = 0
        a_count = 0
        late_count = 0
        leave_count = 0

        if session:
            for r in session.records.all():
                if r.status == "present":
                    p_count += 1
                elif r.status == "absent":
                    a_count += 1
                elif r.status == "late":
                    late_count += 1
                elif r.status == "leave":
                    leave_count += 1

        total_school_students += c_students
        total_school_present += p_count
        total_school_absent += a_count
        total_school_late += late_count
        total_school_leave += leave_count

        class_summaries.append({
            "classId": c.id,
            "className": f"{c.name}-{c.section}",
            "total": c_students,
            "present": p_count,
            "absent": a_count,
            "late": late_count,
            "leave": leave_count,
            "taken": session is not None,
        })

    total_turnout = total_school_present + total_school_late
    present_percent = round((total_turnout / total_school_students * 100), 1) if total_school_students > 0 else 0.0

    return {
        "date": str(date),
        "totalStudents": total_school_students,
        "present": total_school_present,
        "absent": total_school_absent,
        "late": total_school_late,
        "leave": total_school_leave,
        "presentPercent": present_percent,
        "classes": class_summaries,
    }


def get_school_attendance_trend(school, days=7):
    """
    Calculates day-by-day attendance percentage for the last N days.
    """
    today = timezone.localdate()
    trend = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        summary = get_school_attendance_summary(school, date=d)
        trend.append({
            "date": str(d),
            "presentPercent": summary["presentPercent"],
            "total": summary["totalStudents"],
            "present": summary["present"],
        })
    return trend
