# WAVE1_PLAN.md — Wave 1 Implementation Plan

Audit and execution plan for Wave 1 (Daily Use Pack) based on `WAVE1_DESIGN.md`, `AGENTS.md`, `PONYTAIL.md`, and the codebase.

---

## 1. Audit Findings

### 1.1 Exact Import Paths and Model Field Names

#### User
- **File path**: `school-management-system/accounts/models.py`
- **Import path**: `accounts.models.User`
- **Fields**:
  - `id` (BigAutoField)
  - `password`, `last_login`, `is_superuser`, `username`, `first_name`, `last_name`, `email`, `is_staff`, `is_active`, `date_joined`, `groups`, `user_permissions` (from `django.contrib.auth.models.AbstractUser`)
  - `role` (`CharField(max_length=20, choices=[('admin', 'Admin'), ('principal', 'Principal'), ('teacher', 'Teacher'), ('student', 'Student'), ('parent', 'Parent')], default='student')`)
  - `mobile` (`CharField(max_length=15, blank=True)`)
- **Differences / Reality**:
  - `User.mobile` has no regex/digit validation, no normalization, and no `unique=True` constraint.
  - In `db.sqlite3`, existing users have inconsistent formats: e.g. `'07879766536'` (11 chars with leading zero), `'7879766535'` (10 digits), and `''` (blank strings for all test parents and principals).

#### School
- **File path**: `school-management-system/schools/models.py`
- **Import path**: `schools.models.School`
- **Fields**:
  - `id` (BigAutoField)
  - `name` (`CharField(max_length=200)`)
  - `code` (`CharField(max_length=20, unique=True)`)
  - `address` (`TextField()`)
  - `city` (`CharField(max_length=100)`)
  - `phone` (`CharField(max_length=15, blank=True)`)
  - `email` (`EmailField(blank=True)`)
  - `principal` (`OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='principal_school')`)
  - `created_at` (`DateTimeField(auto_now_add=True)`)

#### Teacher
- **File path**: `school-management-system/academics/models.py`
- **Import path**: `academics.models.Teacher`
- **Fields**:
  - `id` (BigAutoField)
  - `user` (`OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teacher_profile')`)
  - `school` (`ForeignKey(School, on_delete=models.CASCADE, related_name='teachers')`)
  - `employee_id` (`CharField(max_length=50, unique=True)`)
  - `qualification` (`CharField(max_length=200, blank=True)`)
  - `joining_date` (`DateField(null=True, blank=True)`)
  - `designation` (`CharField(max_length=100, default='Teacher')`)

#### SchoolClass
- **File path**: `school-management-system/academics/models.py`
- **Import path**: `academics.models.SchoolClass`
- **Fields**:
  - `id` (BigAutoField)
  - `school` (`ForeignKey(School, on_delete=models.CASCADE, related_name='classes')`)
  - `name` (`CharField(max_length=50)`)
  - `section` (`CharField(max_length=10)`)
  - `class_teacher` (`ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, related_name='class_teacher_for')`)
- **Differences / Reality**:
  - The model name is `SchoolClass` (not `Class`).
  - The teacher field is `class_teacher` and points to `academics.Teacher` (not `accounts.User`).
  - There is no AcademicYear foreign key on `SchoolClass`.
  - There is currently no `UniqueConstraint` on `(school, name, section)`.

#### Student
- **File path**: `school-management-system/academics/models.py`
- **Import path**: `academics.models.Student`
- **Fields**:
  - `id` (BigAutoField)
  - `user` (`OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_profile')`)
  - `school` (`ForeignKey(School, on_delete=models.CASCADE, related_name='students')`)
  - `class_section` (`ForeignKey(SchoolClass, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')`)
  - `admission_number` (`CharField(max_length=50, unique=True)`)
  - `date_of_birth` (`DateField(null=True, blank=True)`)
  - `gender` (`CharField(max_length=20, choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')], blank=True)`)
  - `address` (`TextField(blank=True)`)
  - `admission_date` (`DateField(auto_now_add=True)`)
- **Differences / Reality**:
  - The class relationship field is named `class_section` (not `school_class` or `class_id`).
  - `class_section` is **nullable** (`null=True, blank=True`).
  - In `db.sqlite3`, there are currently 5 students, and **all 5 have `class_section = None`**.

---

### 1.2 Latest Migration Names of Existing Apps
Verified from the filesystem:
- `accounts`: `0001_initial` (`accounts/migrations/0001_initial.py`)
- `schools`: `0001_initial` (`schools/migrations/0001_initial.py`)
- `academics`: `0001_initial` (`academics/migrations/0001_initial.py`)
- `core`: no migrations (`__init__.py` only)
- `imports`: no migrations (`__init__.py` only)

All new apps (`academic_year`, `guardians`, `attendance`, `notices`, `audit`) will have their `0001_initial.py` migrations depend explicitly on these exact names.

---

### 1.3 `settings.py` Audit
- **File path**: `school-management-system/config/settings.py`
- `TIME_ZONE`: Currently `'UTC'` (line 119). **It is NOT `"Asia/Kolkata"`**.
  - **Effect of changing to `"Asia/Kolkata"`**:
    1. `timezone.localdate()` will evaluate to Indian Standard Time (UTC+05:30) date. This is critical because school attendance sessions, notice expiries, and academic year checks occur on Indian calendar days. Under UTC, between 00:00 and 05:30 IST, `localdate()` would lag to yesterday; between 18:30 and 23:59 UTC, `localdate()` would be tomorrow.
    2. `USE_TZ = True` ensures all `DateTimeField` values continue to be stored in UTC in SQLite, while Django templates, forms, and admin render in IST.
    3. Existing date records (`admission_date`) are unaffected in SQLite, but future timestamps will display in IST.
- `USE_TZ`: `True` (line 123).
- `ALLOWED_HOSTS`: `['127.0.0.1', 'localhost']` (line 28).
- `INSTALLED_APPS`: List of strings format (lines 33-47).
- `REST_FRAMEWORK` (lines 154-169):
  - `DEFAULT_AUTHENTICATION_CLASSES`: `['rest_framework.authentication.SessionAuthentication']`
  - `DEFAULT_PERMISSION_CLASSES`: `['rest_framework.permissions.IsAuthenticated']`
  - `DEFAULT_RENDERER_CLASSES`: `['rest_framework.renderers.JSONRenderer']`
  - `DEFAULT_THROTTLE_RATES`: `{'anon': '10/minute', 'user': '100/minute', 'auth': '10/min'}`
  - `DEFAULT_THROTTLE_CLASSES`: **not found** in `REST_FRAMEWORK`. Throttling is applied on specific views via `@throttle_classes`.

---

### 1.4 Existing `api/` Structure, View Style, Permissions Helpers, and Tests
- **Views Style**: Function-based views with DRF decorators (`@api_view`, `@permission_classes`, `@throttle_classes`). No class-based views, no ViewSets, no routers.
- **Scoping Helpers**:
  - `user_school(user)` in `api/views.py`: resolves school via `user.principal_school`, `user.teacher_profile.school`, or `user.student_profile.school`.
  - `scoped(qs, user)` in `api/views.py`: returns `qs` for superusers, `qs.filter(school=user.principal_school)` for principals, else `qs.none()`.
  - `get_principal_school(user)` and `get_target_school(request)` in `api/views_admin.py`.
- **Permissions**:
  - `api/permissions.py` defines: `IsPrincipalOrSuperuser`, `IsTeacher`, `IsStudent`, `IsSuperuserOnly`.
  - Missing: `IsParent` (`u.is_authenticated and getattr(u, 'role', '') == 'parent'`).
- **Serializers**:
  - Plain DRF `serializers.ModelSerializer` using CamelCase output fields (`firstName`, `lastName`, `admissionNumber`, `classTeacherName`).
- **Tests**:
  - `api/tests.py`: 35 tests, all passing. Uses standard `TestCase` with `APIClient` and `self.client.force_login(user)`. Enforces tenant isolation between `school_a` and `school_b`.

---

### 1.5 Current Frontend Pages & Mock Data Audit
- `/teacher/attendance` (`Frontend/indoreedu-web/src/app/teacher/attendance/page.tsx`):
  - **Real**: Checks teacher auth via `useRequireRole(['teacher'])`; calls `getMyStudents()` (`GET /api/v1/teacher/my-students/`).
  - **Mock**: Attendance status (`absent`/`present` toggled in local state), turnout percentage, submit button only sets local state `submitted=true` (no API call is made), falls back to `MOCK_ATTENDANCE_ROSTER` when 0 students returned.
- `/parent` (`Frontend/indoreedu-web/src/app/parent/page.tsx`):
  - **Real**: Auth check `useRequireRole(['parent'])`.
  - **Mock**: 100% of data is mock: `MOCK_PARENT_CHILDREN`, `MOCK_PARENT_ATTENDANCE`, `MOCK_PARENT_FEE_DUE`, `MOCK_PARENT_RESULT`, `MOCK_PARENT_NOTICES`. No backend API calls exist today.
- `/admin` (`Frontend/indoreedu-web/src/app/admin/page.tsx`):
  - **Real**: `getDashboardStats()` (`GET /api/v1/dashboard/stats/`) for total counts of teachers, students, classes, subjects.
  - **Mock**: `AdminChartsSection` uses `MOCK_WEEKLY_ATTENDANCE` (bar chart) and `MOCK_DEPARTMENT_FEES`; `AdminActivitySection` uses `MOCK_RECENT_ACTIVITY` and `MOCK_ACADEMIC_NOTICES`.
- `/student` (`Frontend/indoreedu-web/src/app/student/page.tsx`):
  - **Real**: Student name, school name, admission number, class name from `session.user` / `session.student`.
  - **Mock**: Today's attendance (`MOCK_PARENT_ATTENDANCE`), monthly percentage, fee dues, exam results, notices.

---

### 1.6 Conflicts, Flaws, and Risks in `WAVE1_DESIGN.md` (Resolved)
1. **Database Conflict in `Guardian.user`**:
   - Resolved by Decision 1: `Guardian.user` is defined as `ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='guardians')` with `UniqueConstraint(fields=['school', 'user'], condition=Q(user__isnull=False))` allowing multi-school guardian links.
2. **Existing Database Data Gap**:
   - Resolved by Decision 2: No automated seed scripts; admin creates classes and assigns students manually in Django admin. Tests construct their own data fixtures.
3. **Parent Mobile Claim Mismatch**:
   - Resolved by Decision 3: The claim endpoint reads `request.user.mobile` only (returns 400 if empty). Helper `normalize_mobile()` standardizes both to 10 digits for comparison.
4. **Teacher Access Limitation**:
   - Resolved by Decision 4: Class-teacher-only attendance accepted for Wave 1. If a class has no `class_teacher`, only the principal can take attendance.
5. **AcademicYear Dependency**:
   - Resolved: Schools must have an active AcademicYear before taking attendance. Tested in Step 1.


---

## 2. Proposed File List

### 2.1 Backend Files
All new models and migrations are placed strictly in the 5 new apps. Existing apps are untouched.

#### Edited Existing Files (allowed: `config/settings.py`, `api/`):
1. `school-management-system/config/settings.py` (add 5 apps to `INSTALLED_APPS`, set `TIME_ZONE = 'Asia/Kolkata'`, add `'guardian_claim': '5/hour'` to throttle rates).
2. `school-management-system/api/urls.py` (include Wave 1 routes or sub-routers).
3. `school-management-system/api/permissions.py` (add `IsParent`).

#### New Files in `academic_year/`:
- `academic_year/__init__.py`
- `academic_year/apps.py`
- `academic_year/models.py` (`AcademicYear`)
- `academic_year/migrations/__init__.py`
- `academic_year/migrations/0001_initial.py`
- `academic_year/serializers.py`
- `academic_year/services.py`
- `academic_year/views.py`
- `academic_year/tests.py`

#### New Files in `audit/`:
- `audit/__init__.py`
- `audit/apps.py`
- `audit/models.py` (`AuditLog`)
- `audit/migrations/__init__.py`
- `audit/migrations/0001_initial.py`
- `audit/services.py` (`log_action` helper)
- `audit/serializers.py`
- `audit/views.py`
- `audit/tests.py`

#### New Files in `guardians/`:
- `guardians/__init__.py`
- `guardians/apps.py`
- `guardians/models.py` (`Guardian`, `StudentGuardian`)
- `guardians/migrations/__init__.py`
- `guardians/migrations/0001_initial.py`
- `guardians/services.py` (normalize mobile, claim, approve, reject)
- `guardians/serializers.py`
- `guardians/views.py`
- `guardians/tests.py`

#### New Files in `attendance/`:
- `attendance/__init__.py`
- `attendance/apps.py`
- `attendance/models.py` (`AttendanceSession`, `AttendanceRecord`)
- `attendance/migrations/__init__.py`
- `attendance/migrations/0001_initial.py`
- `attendance/services.py` (atomic upsert, statistics, trend calculator)
- `attendance/serializers.py`
- `attendance/views.py`
- `attendance/tests.py`

#### New Files in `notices/`:
- `notices/__init__.py`
- `notices/apps.py`
- `notices/models.py` (`Notice`)
- `notices/migrations/__init__.py`
- `notices/migrations/0001_initial.py`
- `notices/services.py`
- `notices/serializers.py`
- `notices/views.py`
- `notices/tests.py`

#### Files Needing Approval:
- **None**. No changes outside `config/settings.py` and `api/` are requested.

---

### 2.2 Frontend Files (`Frontend/indoreedu-web`)

#### Edited Existing Routes/Components:
1. `src/app/teacher/attendance/page.tsx`: Replace mock toggle and local submit with real `GET attendance/class/<id>/?date=` and `PUT attendance/class/<id>/`.
2. `src/app/parent/page.tsx`: Replace `MOCK_PARENT_CHILDREN` with `GET parent/children/`, replace mock attendance with `GET attendance/student/<id>/`, replace mock notices with `GET notices/`. Add claim modal / empty state.
3. `src/app/admin/page.tsx`: Update `AdminChartsSection.tsx` to fetch `GET attendance/trend/?days=7` and real `GET attendance/summary/` for the KPI card. Update `AdminActivitySection.tsx` with real notices from `GET notices/`.
4. `src/app/student/page.tsx`: Replace mock attendance with real `GET attendance/student/<id>/` and notices with `GET notices/`.
5. `src/components/layout/AdminSidebar.tsx`: Ensure `/admin/notices` and `/admin/guardians` link items are present.
6. `src/types/index.ts`: Add TypeScript types for AcademicYear, Guardian, AttendanceSession, Notice, AuditLog.

#### New Frontend Files:
1. `src/lib/api/wave1.ts`: Client API methods for all Wave 1 endpoints (`getAttendanceRoster`, `saveAttendance`, `getAttendanceTrend`, `getAttendanceSummary`, `getParentChildren`, `claimGuardian`, `getNotices`, `createNotice`, etc.).
2. `src/app/admin/notices/page.tsx`: Notices list + create/edit modal (reusing `DashboardShell`, `indoreedu_admin_dashboard` pattern).
3. `src/app/admin/guardians/page.tsx`: Pending guardian claim approvals + student guardian management (reusing `indoreedu_admin_dashboard` pattern).

---

## 3. Migration Plan

### 3.1 Migration Order and Dependencies
1. `academic_year.0001_initial`:
   - Dependencies: `('schools', '0001_initial')`
2. `audit.0001_initial`:
   - Dependencies: `('schools', '0001_initial')`, `('accounts', '0001_initial')`
3. `guardians.0001_initial`:
   - Dependencies: `('schools', '0001_initial')`, `('academics', '0001_initial')`, `('accounts', '0001_initial')`
4. `attendance.0001_initial`:
   - Dependencies: `('schools', '0001_initial')`, `('academics', '0001_initial')`, `('accounts', '0001_initial')`, `('academic_year', '0001_initial')`
5. `notices.0001_initial`:
   - Dependencies: `('schools', '0001_initial')`, `('academics', '0001_initial')`, `('accounts', '0001_initial')`

### 3.2 Verification
Run:
```bash
python manage.py makemigrations --check --dry-run
```
Expected result: "No changes detected" for `accounts`, `schools`, `academics`, `core`, `imports`.

---

## 4. API Contract

All endpoints live under `/api/v1/`, use session auth + CSRF, return camelCase JSON, and return standard DRF error payloads (`{"detail": "..."}` or `{"fieldName": ["..."]}`).

### 4.1 Academic Year
1. `GET /api/v1/academic-years/`
   - **Permission**: `IsPrincipalOrSuperuser`
   - **Response 200**:
     ```json
     [
       {
         "id": 1,
         "name": "2026-27",
         "startDate": "2026-04-01",
         "endDate": "2027-03-31",
         "isCurrent": true,
         "school": 1
       }
     ]
     ```
2. `POST /api/v1/academic-years/`
   - **Permission**: `IsPrincipalOrSuperuser`
   - **Request JSON**:
     ```json
     {
       "name": "2026-27",
       "startDate": "2026-04-01",
       "endDate": "2027-03-31",
       "isCurrent": true
     }
     ```
   - **Response 201**: Returns created AcademicYear object. Unsets previous `isCurrent=True` atomically.
   - **Errors**: `400` on validation errors (e.g. `endDate <= startDate`, duplicate name).

### 4.2 Guardians
1. `GET /api/v1/students/<id>/guardians/`
   - **Permission**: `IsPrincipalOrSuperuser` (must match student's school)
   - **Response 200**:
     ```json
     [
       {
         "id": 10,
         "guardianId": 5,
         "fullName": "Suresh Sharma",
         "mobile": "9826011111",
         "email": "suresh@example.com",
         "relation": "father",
         "isPrimary": true,
         "linkStatus": "approved",
         "linkedUsername": "suresh_p"
       }
     ]
     ```
2. `POST /api/v1/students/<id>/guardians/`
   - **Permission**: `IsPrincipalOrSuperuser`
   - **Request JSON**:
     ```json
     {
       "fullName": "Suresh Sharma",
       "mobile": "9826011111",
       "email": "suresh@example.com",
       "relation": "father",
       "isPrimary": true
     }
     ```
   - **Response 201**: Created/linked `StudentGuardian`. Creates or reuses `Guardian(school, mobile)`.
   - **Errors**: `400` invalid phone format, `404` student not found.
3. `DELETE /api/v1/students/<id>/guardians/<guardianId>/`
   - **Permission**: `IsPrincipalOrSuperuser`
   - **Response 200**: `{"detail": "Guardian link removed"}`
4. `POST /api/v1/guardians/claim/`
   - **Permission**: `IsParent`
   - **Throttle**: 5/hour
   - **Request JSON**: `{}` (ignores any mobile in body; strictly uses `request.user.mobile`).
   - **Response 200**:
     ```json
     {
       "pendingCount": 1,
       "matchedSchools": ["SGSITS Indore"]
     }
     ```
   - **Errors**: `400` if parent user has no mobile set.
5. `GET /api/v1/guardians/link-requests/`
   - **Permission**: `IsPrincipalOrSuperuser`
   - **Response 200**:
     ```json
     [
       {
         "id": 5,
         "guardianName": "Suresh Sharma",
         "guardianMobile": "9826011111",
         "requestedUser": {
           "id": 12,
           "username": "parent_suresh",
           "name": "Suresh Sharma",
           "mobile": "9826011111"
         },
         "children": [
           { "id": 1, "name": "Aarav Sharma", "className": "10-A" }
         ]
       }
     ]
     ```
6. `POST /api/v1/guardians/link-requests/<guardianId>/approve/`
   - **Permission**: `IsPrincipalOrSuperuser`
   - **Response 200**: `{"detail": "Link request approved"}`
7. `POST /api/v1/guardians/link-requests/<guardianId>/reject/`
   - **Permission**: `IsPrincipalOrSuperuser`
   - **Response 200**: `{"detail": "Link request rejected"}`
8. `GET /api/v1/parent/children/`
   - **Permission**: `IsParent`
   - **Response 200**:
     ```json
     [
       {
         "id": 1,
         "name": "Aarav Sharma",
         "admissionNumber": "A001",
         "schoolId": 1,
         "schoolName": "SGSITS Indore",
         "className": "10-A",
         "todayStatus": "present"
       }
     ]
     ```

### 4.3 Attendance
1. `GET /api/v1/attendance/class/<classId>/?date=YYYY-MM-DD`
   - **Permission**: `IsPrincipalOrSuperuser` or `IsTeacher` (class_teacher only)
   - **Response 200**:
     ```json
     {
       "classId": 3,
       "className": "10-A",
       "date": "2026-10-20",
       "exists": true,
       "students": [
         {
           "studentId": 1,
           "name": "Aarav Sharma",
           "admissionNumber": "A001",
           "status": "present",
           "remark": ""
         }
       ]
     }
     ```
   - Note: If `exists: false`, all students default to `"present"`.
2. `PUT /api/v1/attendance/class/<classId>/`
   - **Permission**: `IsPrincipalOrSuperuser` or `IsTeacher` (class_teacher only; today only for teachers)
   - **Request JSON**:
     ```json
     {
       "date": "2026-10-20",
       "records": [
         { "studentId": 1, "status": "present", "remark": "" },
         { "studentId": 2, "status": "absent", "remark": "Sick" }
       ]
     }
     ```
   - **Response 200**: `{"detail": "Attendance saved successfully", "presentCount": 1, "totalCount": 2}`
   - **Errors**: `400` foreign/missing studentId, future date, outside academic year; `403` teacher backdating.
3. `GET /api/v1/attendance/summary/?date=YYYY-MM-DD`
   - **Permission**: `IsPrincipalOrSuperuser`
   - **Response 200**:
     ```json
     {
       "date": "2026-10-20",
       "schoolTotal": 120,
       "schoolPresent": 110,
       "presentPercent": 91.6,
       "classes": [
         {
           "classId": 3,
           "className": "10-A",
           "total": 30,
           "present": 28,
           "absent": 2,
           "late": 0,
           "leave": 0,
           "taken": true
         }
       ]
     }
     ```
4. `GET /api/v1/attendance/trend/?days=7`
   - **Permission**: `IsPrincipalOrSuperuser`
   - **Response 200**:
     ```json
     [
       { "date": "2026-10-14", "day": "Wed", "presentPercent": 92.0 },
       { "date": "2026-10-15", "day": "Thu", "presentPercent": 89.5 }
     ]
     ```
5. `GET /api/v1/attendance/student/<studentId>/?month=YYYY-MM`
   - **Permission**: Linked Parent, Class Teacher, Principal, or Student themself
   - **Response 200**:
     ```json
     {
       "studentId": 1,
       "month": "2026-10",
       "totalDays": 18,
       "present": 16,
       "absent": 2,
       "late": 0,
       "leave": 0,
       "presentPercent": 88.9,
       "records": [
         { "date": "2026-10-01", "status": "present" },
         { "date": "2026-10-02", "status": "absent" }
       ]
     }
     ```

### 4.4 Notices
1. `GET /api/v1/notices/`
   - **Permission**: `IsAuthenticated`
   - **Filter**: Role and school scoped. Hides expired notices for non-principals. Pinned notices first.
   - **Response 200**: List of Notice objects.
2. `POST /api/v1/notices/`
   - **Permission**: `IsPrincipalOrSuperuser`
   - **Request JSON**:
     ```json
     {
       "title": "Annual Sports Meet",
       "body": "Events schedule attached...",
       "audience": "all",
       "targetClassIds": [],
       "isPinned": true,
       "expiresOn": "2026-11-01"
     }
     ```
   - **Response 201**: Notice object.
3. `PATCH /api/v1/notices/<id>/`, `DELETE /api/v1/notices/<id>/`
   - **Permission**: `IsPrincipalOrSuperuser`

### 4.5 Audit
1. `GET /api/v1/audit/?action=&limit=50`
   - **Permission**: `IsPrincipalOrSuperuser` (scoped to school for principal; all for superuser)
   - **Response 200**: Paginated list of AuditLog records.

---

## 5. Test Plan

Grouped by app in standard Django `TestCase`:

### `academic_year` Tests (`academic_year/tests.py`)
- `test_create_academic_year_principal`: Principal creates an academic year for their school.
- `test_academic_year_date_constraint`: `end_date <= start_date` raises ValidationError.
- `test_single_current_academic_year_per_school`: Setting a new year `is_current=True` unsets previous current year.
- `test_academic_year_tenant_isolation`: Principal A cannot view or modify Principal B's academic years.

### `guardians` Tests (`guardians/tests.py`)
- `test_add_guardian_to_student`: Principal adds guardian; creates `Guardian` with `unlinked` status.
- `test_sibling_guardian_deduplication`: Same mobile in same school reuses existing `Guardian` row.
- `test_claim_flow_matching_own_mobile`: Parent calls claim; only `request.user.mobile` is used.
- `test_claim_flow_throttling`: 6th claim request within an hour returns HTTP 429.
- `test_claim_does_not_auto_approve`: Status becomes `pending`, NOT `approved`.
- `test_principal_approve_claim`: Links `user = requested_user`, status `approved`.
- `test_principal_reject_claim`: Clears `requested_user`, resets to `unlinked`.
- `test_parent_sees_only_approved_children`: Unlinked or pending children are not visible in `GET /api/v1/parent/children/`.
- `test_guardian_tenant_isolation`: Principal A cannot see or approve Principal B's guardian requests.

### `attendance` Tests (`attendance/tests.py`)
- `test_get_roster_defaults_to_present`: When no session exists, all students default to `present`.
- `test_save_attendance_atomic_upsert`: Upsert creates 1 session and N records idempotently.
- `test_foreign_student_rejected`: Posting studentId not in class raises 400 and leaves no records.
- `test_teacher_cannot_mark_other_class`: Teacher A cannot mark Class B (HTTP 403).
- `test_teacher_cannot_backdate_or_future_date`: Teacher posting past or future date gets HTTP 403 / 400.
- `test_principal_can_edit_past_date_with_audit`: Principal edit of past attendance creates audit log before/after.
- `test_attendance_summary_and_trend`: Summary returns accurate class and school percentages.
- `test_student_and_parent_monthly_view`: Student and approved parent can view monthly attendance history.

### `notices` Tests (`notices/tests.py`)
- `test_notice_visibility_matrix`:
  - Principal sees all school notices.
  - Teacher sees `all`, `teachers`, and classes they teach.
  - Parent sees `all`, `parents`, and their approved children's classes.
  - Student sees `all` and their own class.
- `test_expired_notice_hidden_from_non_principals`: Expired notice filtered out for students/parents.
- `test_notice_tenant_isolation`: School A notice never visible to School B users.

### `audit` Tests (`audit/tests.py`)
- `test_audit_records_written_on_attendance_edit`: Session edit writes `attendance.update` with before/after diff.
- `test_audit_records_written_on_guardian_approval`: Approval writes `guardian.approve`.
- `test_audit_api_is_read_only`: POST/PUT/DELETE to `/api/v1/audit/` return HTTP 405.
- `test_audit_tenant_isolation`: Principal A only sees School A audit logs.

---

## 6. Frontend Plan

### 6.1 Route-by-Route Breakdown

| Route | Data Becoming Real | Data Staying Mock (`isSample: true`) | New Components Needed | Reused Stitch Screen Design |
|---|---|---|---|---|
| `/teacher/attendance` | Real class roster from `GET attendance/class/<id>/`, real save via `PUT attendance/class/<id>/`, dynamic present/absent count | Fallback to mock only if class has 0 students | Attendance confirmation dialog | `indoreedu_teacher_attendance` |
| `/parent` | Child switcher from `GET parent/children/`, real daily attendance, real monthly calendar from `GET attendance/student/<id>/`, real notices from `GET notices/` | Fee breakdown, Bus tracking, Term results | Guardian claim empty state modal | `indoreedu_parent_mobile_home` |
| `/admin` | "Present Today" KPI from `GET attendance/summary/`, Weekly attendance trend chart from `GET attendance/trend/`, Notices summary from `GET notices/` | Department fees breakdown, System activities log | Chart real-data binding | `indoreedu_admin_dashboard` |
| `/student` | Real today attendance status & monthly turnout from `GET attendance/student/<id>/`, real notices from `GET notices/` | Fee dues, Examination report cards | None (inline update) | `DashboardShell` |
| `/admin/notices` *(New)* | Real notices list, real create/edit/delete/pin modal | None | NoticeFormModal, NoticeTable | `indoreedu_admin_dashboard` |
| `/admin/guardians` *(New)* | Pending link requests, approve/reject buttons, add guardian form | None | LinkRequestTable, AddGuardianModal | `indoreedu_admin_dashboard` |

---

## 7. Implementation Order

Each step is small, self-contained, and independently verifiable.

### Step 1: `academic_year`
- **Files**: `academic_year/` app models, migrations, serializers, views, tests; update `config/settings.py` (`INSTALLED_APPS`).
- **Checks**:
  - `python manage.py makemigrations academic_year`
  - `python manage.py makemigrations --check --dry-run` (verify 0 changes in existing apps)
  - `python manage.py test academic_year`
- **Manual Verification**: Log into Django admin or call `POST /api/v1/academic-years/` as principal, set `2026-27` as current.

### Step 2: `audit`
- **Files**: `audit/` app models, migrations, service `log_action()`, serializers, views, tests; update `config/settings.py`.
- **Checks**:
  - `python manage.py makemigrations audit`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py test audit`
- **Manual Verification**: Trigger a logged action, verify row in `GET /api/v1/audit/`.

### Step 3: `guardians` & Parent Claim Flow
- **Files**: `guardians/` app models, migrations, service functions (normalize phone, claim, approve), serializers, views, tests; update `config/settings.py`.
- **Checks**:
  - `python manage.py makemigrations guardians`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py test guardians`
- **Manual Verification**: Principal adds guardian for student; parent logs in, calls claim; principal approves claim; parent can fetch `/api/v1/parent/children/`.

### Step 4: `attendance`
- **Files**: `attendance/` app models, migrations, atomic upsert service, serializers, views, tests; update `config/settings.py`.
- **Checks**:
  - `python manage.py makemigrations attendance`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py test attendance`
- **Manual Verification**: Teacher opens attendance for today, marks 1 absent, submits; verify session and records saved; verify principal summary updates.

### Step 5: `notices`
- **Files**: `notices/` app models, migrations, audience filtering service, serializers, views, tests; update `config/settings.py`.
- **Checks**:
  - `python manage.py makemigrations notices`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py test notices`
- **Manual Verification**: Principal posts pinned notice for 'parents'; parent sees it; student of another school does not.

### Step 6: Frontend API & Types
- **Files**: `src/types/index.ts`, `src/lib/api/wave1.ts`.
- **Checks**: `npm run lint`, `npx tsc --noEmit`.

### Step 7: Frontend Teacher Attendance
- **Files**: `src/app/teacher/attendance/page.tsx`.
- **Checks**: `npx tsc --noEmit`.
- **Manual Verification**: Log in as teacher, open `/teacher/attendance`, mark status, click Submit, verify toast and persisted DB data.

### Step 8: Frontend Parent Portal
- **Files**: `src/app/parent/page.tsx`.
- **Checks**: `npx tsc --noEmit`.
- **Manual Verification**: Log in as linked parent, verify real child selector, real attendance status, real notices.

### Step 9: Frontend Admin Screens
- **Files**: `src/app/admin/page.tsx`, `src/components/admin/AdminChartsSection.tsx`, `src/components/admin/AdminActivitySection.tsx`, `src/app/admin/notices/page.tsx`, `src/app/admin/guardians/page.tsx`.
- **Checks**: `npx tsc --noEmit`, `npm run build`.
- **Manual Verification**: Verify "Present Today" KPI, weekly trend chart, notice creation modal, and guardian approval workflow.

### Step 10: Frontend Student Dashboard
- **Files**: `src/app/student/page.tsx`.
- **Checks**: `npx tsc --noEmit`, `npm run build`.
- **Manual Verification**: Student sees their real daily attendance and school notices.

---

## 8. Decisions Applied and Confirmed

1. **`Guardian.user` Relationship and Constraint**:
   - **Decision**: `Guardian.user` is `ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="guardians")` with `UniqueConstraint(fields=["school", "user"], condition=Q(user__isnull=False))`. A parent User can be linked to at most one Guardian record per school, across multiple schools.

2. **Existing Data & Seeding**:
   - **Decision**: No seed script. The user will create classes and assign students manually via Django admin. Tests construct their own isolated data fixtures.

3. **Parent Mobile Claim**:
   - **Decision**: The claim endpoint reads `request.user.mobile` only. If empty, return `400 {"detail": "Add your mobile number to your account first."}`. Never read a mobile from the request body. Add helper `normalize_mobile()` (extract digits, keep last 10 digits) for comparing `Guardian.mobile` and `User.mobile`. Existing user models/code are not modified.

4. **Class Teacher Only Attendance**:
   - **Decision**: Accepted for Wave 1. If a class has no assigned `class_teacher`, only the school Principal (or superuser) can take attendance.

5. **`TIME_ZONE` Setting Change**:
   - **Decision**: Set `TIME_ZONE = "Asia/Kolkata"` in `config/settings.py`. Audit confirmed zero occurrences of `timezone.now().date()`, `datetime.now()`, `date.today()`, or `datetime.today()` in application code, ensuring zero breaking impact.

