# Wave 1 Design: Daily Use Pack

Scope: academic year (minimal), parent-student link, daily attendance, notices, audit log.
Out of scope: file uploads, class-subject mapping, SMS/WhatsApp, fees, exams, reports.

Existing models (`User`, `School`, `Teacher`, `SchoolClass`, `Student`, `Subject`) are NOT modified. New data lives in new Django apps that only add foreign keys pointing at the existing tables.

## 1. New apps and models

Five small apps. If the audit shows two of them are trivially small, the plan may merge them, but never put models into an existing app.

| App | Models |
|---|---|
| `academic_year` | AcademicYear |
| `guardians` | Guardian, StudentGuardian |
| `attendance` | AttendanceSession, AttendanceRecord |
| `notices` | Notice |
| `audit` | AuditLog |

### AcademicYear
| Field | Notes |
|---|---|
| school | FK School, CASCADE |
| name | CharField(20), e.g. "2026-27" |
| start_date, end_date | DateField |
| is_current | BooleanField, default False |

Constraints: unique (school, name); CheckConstraint end_date > start_date; UniqueConstraint on (school) where is_current=True (only one current year per school).

### Guardian
One row per (school, mobile). Siblings share one Guardian row.
| Field | Notes |
|---|---|
| school | FK School, CASCADE |
| full_name | CharField(150) |
| mobile | CharField(15), stored digits only, normalized |
| email | EmailField, blank |
| user | FK User, null, blank, SET_NULL, related_name="guardians". Set ONLY when the school approves the link. |
| requested_user | FK User, null, blank, SET_NULL. A parent who claimed this row, waiting for approval. |
| link_status | choices: unlinked, pending, approved. Default unlinked. |
| decided_by, decided_at | FK User null, DateTime null |

Constraints: unique (school, mobile); UniqueConstraint(fields=["school", "user"], condition=Q(user__isnull=False)). `user` must be a User with role "parent" (validate in service layer). A parent User can be linked to one Guardian row per school across multiple schools.

### StudentGuardian
| Field | Notes |
|---|---|
| student | FK Student, CASCADE |
| guardian | FK Guardian, CASCADE |
| relation | choices: father, mother, guardian, other |
| is_primary | BooleanField default False |

Constraints: unique (student, guardian); at most one primary per student (conditional UniqueConstraint). Guardian.school must equal Student.school (service-layer check).

### AttendanceSession
One per class per day.
| Field | Notes |
|---|---|
| school | FK School (denormalized for fast scoping) |
| school_class | FK SchoolClass |
| academic_year | FK AcademicYear |
| date | DateField |
| taken_by | FK User, SET_NULL |
| created_at, updated_at | auto |

Constraints: unique (school_class, date). Index (school, date). Service layer checks school_class.school == school.

### AttendanceRecord
| Field | Notes |
|---|---|
| session | FK AttendanceSession, CASCADE |
| student | FK Student, CASCADE |
| status | choices: present, absent, late, leave |
| remark | CharField(200), blank |

Constraints: unique (session, student). Index (student, session). All students of the class get a row on save (about 30-60 rows).

### Notice
| Field | Notes |
|---|---|
| school | FK School, CASCADE |
| title | CharField(200) |
| body | TextField |
| audience | choices: all, parents, teachers, classes |
| target_classes | ManyToMany SchoolClass, blank (required when audience = classes) |
| is_pinned | BooleanField default False |
| expires_on | DateField null |
| created_by | FK User, SET_NULL |
| created_at, updated_at | auto |

Index (school, -created_at). Target classes must belong to the same school.

### AuditLog (append-only)
| Field | Notes |
|---|---|
| school | FK School, null, SET_NULL |
| actor | FK User, null, SET_NULL |
| action | CharField(50): attendance.create, attendance.update, notice.create, notice.update, notice.delete, guardian.add, guardian.remove, guardian.claim, guardian.approve, guardian.reject, academic_year.create, academic_year.set_current |
| object_type, object_id | CharField / PositiveBigInteger |
| changes | JSONField (before/after for edits, small) |
| ip_address | GenericIPAddressField null |
| created_at | auto |

Index (school, -created_at). No update or delete through API or Django admin (read-only admin). Written by explicit service functions in each app (not signals), inside the same transaction as the change.

## 2. Parent-student link flow (security critical)

Mobile numbers are not verified (no OTP yet), so a mobile match must never grant access on its own.

1. Principal adds a guardian to a student: `POST students/<id>/guardians/` creates or reuses Guardian(school, mobile) and the StudentGuardian row. Status starts `unlinked`.
2. Parent registers normally (role parent) and sets `User.mobile`.
3. Parent calls `POST guardians/claim/`. The server reads `request.user.mobile` only. If it is empty, returns `400 {"detail": "Add your mobile number to your account first."}`. Never reads a mobile from the request body. A helper `normalize_mobile()` (digits only, keep last 10 digits) compares normalized values of `Guardian.mobile` and `User.mobile`. Finds Guardian rows with matching normalized mobile and link_status `unlinked`, sets `requested_user` = parent and status `pending`. Throttled (5 per hour).
4. Principal sees the pending list (parent's name, username, mobile, guardian name, children) and approves or rejects. Approve sets `user` = requested_user and status `approved`. Reject resets to `unlinked` and clears requested_user.
5. Only Guardian rows with status `approved` give a parent access to a student's data.

Later (Wave 4 notification engine) an OTP to the guardian mobile can replace manual approval.

## 3. Access rules

| Role | Attendance | Notices | Guardians | Audit |
|---|---|---|---|---|
| Superuser | read all | read all | read all | read all |
| Principal | read and write own school, any past date within the current year | create, edit, delete, read own school | add/remove, approve/reject own school | read own school |
| Teacher | read and write only classes where they are class_teacher, only for today | read notices for all/teachers and for classes they teach | none | none |
| Parent | read only linked (approved) children | read notices for their children's schools and classes (audience all, parents, or matching class) | claim own mobile only | none |
| Student | read own attendance | read audience all and their class | none | none |

Notes:
- "Today" means `timezone.localdate()` with `TIME_ZONE = "Asia/Kolkata"` set in `config/settings.py`.
- Future dates are rejected. Dates outside the current academic year are rejected.
- Editing a session after the day it was taken: principal only, always audited with before/after.
- Teacher permission is class-teacher only (there is no subject-teacher mapping yet). If a class has no class_teacher, only the principal can take attendance.
- Never return another school's or another family's data. Every queryset starts from a scoped base.
- Data seeding: No automated seed scripts; admin creates classes and assigns students manually in Django admin. Tests construct their own data fixtures.

## 4. Attendance rules
- Teacher screen loads the roster with every student defaulting to `present` when no session exists yet.
- Save is one atomic upsert: create or update the session, then create or update all records in one transaction. Idempotent.
- All posted studentIds must belong to the class; extra or missing students are rejected.
- Present percentage = (present + late) / total. Absent and leave are not present.
- A class counts as "not taken today" if it has students but no session for today.

## 5. API (all under `/api/v1/`, session auth + CSRF, camelCase JSON, DRF-style field errors)

### Academic year (principal, superuser)
- `GET academic-years/` list for the school
- `POST academic-years/` {name, startDate, endDate, isCurrent}; if isCurrent, the previous current year is unset in the same transaction

### Guardians
- `GET students/<id>/guardians/`, `POST students/<id>/guardians/` {fullName, mobile, relation, isPrimary}, `DELETE students/<id>/guardians/<guardianId>/` (principal)
- `POST guardians/claim/` (parent, throttled) returns {pending: n, schools: [...]}
- `GET guardians/link-requests/` (principal) pending list
- `POST guardians/link-requests/<guardianId>/approve/` and `.../reject/` (principal)
- `GET parent/children/` (parent) approved children: id, name, school, className, todayStatus

### Attendance
- `GET attendance/class/<classId>/?date=` returns {classId, date, exists, students: [{studentId, name, admissionNumber, status, remark}]}; defaults to today and status present when not yet taken
- `PUT attendance/class/<classId>/` {date, records: [{studentId, status, remark}]} atomic upsert
- `GET attendance/summary/?date=` (principal) per class {classId, className, total, present, absent, late, leave, taken} plus school totals and presentPercent
- `GET attendance/trend/?days=7` (principal) per day presentPercent for the school
- `GET attendance/student/<studentId>/?month=YYYY-MM` (linked parent, class teacher, principal, the student themself) days with status and monthly counts

### Notices
- `GET notices/` role-filtered, pinned first then newest, hides expired for non-principals
- `POST notices/` (principal) {title, body, audience, targetClassIds, isPinned, expiresOn}
- `PATCH notices/<id>/`, `DELETE notices/<id>/` (principal)

### Audit
- `GET audit/?action=&limit=50` (principal own school, superuser all), read only

## 6. Frontend changes enabled by Wave 1
- `/teacher/attendance`: real roster from the new endpoint, all present by default, tap to mark absent/late/leave, Submit saves, success dialog stays. Sample roster fallback only when the class has no students.
- `/parent`: real children switcher, real attendance (today plus monthly calendar), real notices; empty state with "Link your child" button calling claim.
- `/admin`: "Present Today" KPI and weekly trend chart become real; notices list real.
- New principal screens (no Stitch design exists, reuse existing components and Tailwind classes): `/admin/notices` (list + create form), `/admin/guardians` (pending approvals, plus add guardian from a student row).
- `/student`: real own attendance summary.
- Fees, results, bus route and other tiles stay mock with `isSample: true`.

## 7. Tests required
- Tenant isolation for every endpoint (School A principal cannot read or write School B).
- Parent sees only approved children; a pending or unlinked parent gets none.
- Claim ignores any mobile in the request body, is throttled, and never auto-approves.
- Attendance: teacher cannot take another class, cannot backdate, principal can edit with audit before/after, duplicate sessions impossible, foreign studentIds rejected, partial failure leaves nothing.
- Notices visibility matrix by role and audience, expiry hiding.
- Audit rows exist for each audited action, and the API offers no way to edit or delete them.
- Constraints: one current academic year per school, one primary guardian per student, unique (class, date).

## 8. Privacy
- No Aadhaar numbers, no photos or documents in Wave 1.
- Guardian mobile numbers are visible to the principal of that school only (not to teachers, not in public endpoints).
- Never log request bodies containing mobile numbers or passwords.
