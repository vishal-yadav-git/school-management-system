# WAVE2_PLAN.md — Wave 2 Implementation Plan ("Onboarding Pack")

Audit, architecture, and step-by-step execution plan for Wave 2 (Onboarding Pack) based on `AGENTS.md`, `PONYTAIL.md`, the codebase, and user decisions.

---

## 1. Audit Findings (Facts from Code)

### 1.1 Existing Models and Database Reality

#### User (`accounts.models.User`)
- **File path**: `school-management-system/accounts/models.py`
- **Fields**:
  - `id`, `username` (`unique=True`), `password`, `email`, `first_name`, `last_name`, `is_staff`, `is_active`, `is_superuser`, `date_joined`.
  - `role`: `CharField(max_length=20, choices=[('admin', 'Admin'), ('principal', 'Principal'), ('teacher', 'Teacher'), ('student', 'Student'), ('parent', 'Parent')], default='student')`.
  - `mobile`: `CharField(max_length=15, blank=True)`.
- **Audit Findings**:
  - `User.mobile` has **no database `unique=True` constraint**. Multiple users can have blank or identical mobile numbers in DB.
  - In student bulk imports, student `User.mobile` will remain blank (`""`).
  - Guardian mobile is stored exclusively in `guardians.Guardian.mobile`.
  - For parent user accounts created during student import: lookup and creation are strictly by `username = normalized_10_digit_mobile` (never by `User.mobile`), ensuring deterministic sibling reuse.
  - No password security or expiry tracking exists on `User`.

#### School (`schools.models.School`)
- **File path**: `school-management-system/schools/models.py`
- **Fields**:
  - `id`, `name`, `code` (`unique=True`), `address`, `city`, `phone`, `email`, `created_at`.
  - `principal`: `OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='principal_school')`.
- **Audit Findings**:
  - `School.principal` is a **`OneToOneField`**. A single User cannot be set as `School.principal` on multiple schools simultaneously.
  - `School` has **no status field** (`pending`, `active`). Per `AGENTS.md` Rule 1, `schools.School` cannot be modified. Status will live in `organizations.SchoolOrganization.status`.

#### Subject (`academics.models.Subject`)
- **File path**: `school-management-system/academics/models.py`
- **Fields**: `id`, `school` (FK `School`), `name`, `code`.
- **Audit Findings**:
  - `Subject` has no teacher assignment, class section link, or syllabus linkage.
  - No `UniqueConstraint` currently exists on `(school, code)`.
  - Cannot be edited. All syllabus units, topics, and class-subject-teacher mappings must live in new tables pointing to `Subject`.

#### Guardian & StudentGuardian (`guardians.models.Guardian`, `guardians.models.StudentGuardian`)
- **File path**: `school-management-system/guardians/models.py`
- **Audit Findings**:
  - `link_status` lives on **`Guardian`** (`STATUS_CHOICES = [("unlinked", "Unlinked"), ("pending", "Pending"), ("approved", "Approved")]`).
  - `StudentGuardian` links `student` to `guardian` with `relation` (`father`, `mother`, `guardian`, `other`) and `is_primary` (`BooleanField`).
  - `StudentGuardian` has **no status field**.
  - `Guardian` enforces `UniqueConstraint(fields=["school", "mobile"])`.
  - Principal student imports will deduplicate `Guardian` by `(school, mobile)`, set `link_status="approved"`, link to parent `User` (`username=normalized_mobile`), and create `StudentGuardian(is_primary=True, relation=...)`.

#### AuditLog (`audit.models.AuditLog`)
- **File path**: `school-management-system/audit/models.py`
- **Audit Findings**:
  - `action`: `CharField(max_length=50)` with **no choices restrictions**.
  - All Wave 2 actions follow the standard "object.verb" naming:
    - `credentials.reset`
    - `import.teachers`
    - `import.students`
    - `permission.grant`
    - `permission.revoke`
    - `campus.switch`
  - Max length is 50; no schema migration is required in the `audit` app.

### 1.2 Openpyxl & Package Dependencies
- **Audit Finding**: `openpyxl` is not installed in `.venv` and not listed in `requirements.txt`.
- **User Decision**: Approved. Add `openpyxl>=3.1.2` to `requirements.txt` and install into `.venv`. No other new packages.

---

## 2. Proposed File List

### 2.1 Backend New Apps & Files

#### 1. `organizations` App
- `school-management-system/organizations/__init__.py`
- `school-management-system/organizations/apps.py`
- `school-management-system/organizations/models.py`:
  - `Organization` (`name`, `code`, `owner` [FK User], `created_at`)
  - `SchoolOrganization` (`school` [OneToOne School], `organization` [FK Organization], `status` ['pending','active'], `is_main_campus`, `created_at`)
  - `OrganizationMember` (`organization` [FK], `user` [FK], `role` ['owner','admin','viewer'], `created_at`, Unique `(organization, user)`)
  - `EmailVerificationToken` (`user`, `token_hash` [SHA-256], `expires_at`, `is_used`, `created_at`)
- `school-management-system/organizations/services.py`:
  - `create_organization_with_campus()` (creates Org + School + Owner + SchoolOrg)
  - `send_verification_email()` (console backend in dev/test, SMTP in prod)
  - `verify_email_token(raw_token)` (hashes token, verifies expiry, activates SchoolOrganization.status)
  - `switch_active_campus(user, target_school_id)` (verifies membership on every switch)
  - `get_active_school_for_user(request)` (re-validates membership on EVERY request)
- `school-management-system/organizations/views.py`
- `school-management-system/organizations/serializers.py`
- `school-management-system/organizations/admin.py`
- `school-management-system/organizations/tests.py`

#### 2. `credentials` App
- `school-management-system/credentials/__init__.py`
- `school-management-system/credentials/apps.py`
- `school-management-system/credentials/models.py`:
  - `UserSecurity` (`user` [OneToOne User], `must_change_password` [bool], `password_changed_at`, `created_at`, `updated_at`)
- `school-management-system/credentials/services.py`:
  - `generate_username(school_code, role, identifier)` (`<schoolcode>-<id>` format, sanitized)
  - `generate_random_password(length=10)` (letters + digits + symbols meeting Django validators)
  - `reset_password_for_user(actor, target_user)` (resets password, sets must_change_password=True, logs `credentials.reset`)
  - `build_credentials_sheet(credentials_rows, school_name)` (in-memory openpyxl workbook)
- `school-management-system/credentials/views.py`
- `school-management-system/credentials/serializers.py`
- `school-management-system/credentials/admin.py`
- `school-management-system/credentials/tests.py`

#### 3. `importers` App
- `school-management-system/importers/__init__.py`
- `school-management-system/importers/apps.py`
- `school-management-system/importers/services.py`:
  - `sanitize_cell_formula(val)` (formula injection defense: strips/escapes `=`, `+`, `-`, `@`, `\t`, `\r`)
  - `generate_teacher_template()` (openpyxl streaming)
  - `generate_student_template()` (openpyxl streaming)
  - `validate_teacher_import(file_obj, school)` (dry-run, row-level errors, global employee_id uniqueness check)
  - `validate_student_import(file_obj, school)` (dry-run, row-level errors, global admission_number uniqueness check, guardian format check)
  - `commit_teacher_import(validated_payload, actor, school)` (atomic transaction: User, Teacher, UserSecurity, `import.teachers` AuditLog, returns openpyxl workbook)
  - `commit_student_import(validated_payload, actor, school)` (atomic transaction: User, Student, Guardian deduplication by `(school, mobile)`, `link_status='approved'`, parent user by `username=mobile`, StudentGuardian, UserSecurity, `import.students` AuditLog, returns openpyxl workbook)
- `school-management-system/importers/views.py`
- `school-management-system/importers/tests.py`

#### 4. `teacher_assignments` App
- `school-management-system/teacher_assignments/__init__.py`
- `school-management-system/teacher_assignments/apps.py`
- `school-management-system/teacher_assignments/models.py`:
  - `TeacherPermission` (`school`, `teacher`, `permission_key`, `granted_by`, `granted_at`, Unique `(school, teacher, permission_key)`)
  - `ClassSubjectTeacher` (`school`, `school_class`, `subject`, `teacher`, `assigned_at`, Unique `(school_class, subject)`)
- `school-management-system/teacher_assignments/services.py`:
  - `grant_permission(school, teacher, key, actor)` (logs `permission.grant`)
  - `revoke_permission(school, teacher, key, actor)` (logs `permission.revoke`)
  - `has_teacher_permission(teacher, key)`
  - `assign_subject_teacher(school, school_class, subject, teacher, actor)`
- `school-management-system/teacher_assignments/views.py`
- `school-management-system/teacher_assignments/serializers.py`
- `school-management-system/teacher_assignments/admin.py`
- `school-management-system/teacher_assignments/tests.py`

#### 5. `syllabus` App
- `school-management-system/syllabus/__init__.py`
- `school-management-system/syllabus/apps.py`
- `school-management-system/syllabus/models.py`:
  - `Unit` (`subject` [FK academics.Subject], `unit_number`, `title`, `description`, `created_at`, Unique `(subject, unit_number)`)
  - `Topic` (`unit` [FK Unit], `topic_number`, `title`, `description`, `status` ['not_started','in_progress','completed'], `completed_at`, `created_at`, Unique `(unit, topic_number)`)
- `school-management-system/syllabus/services.py`
- `school-management-system/syllabus/views.py`
- `school-management-system/syllabus/serializers.py`
- `school-management-system/syllabus/admin.py`
- `school-management-system/syllabus/tests.py`

### 2.2 Backend Edited Existing Files
- `requirements.txt` (Add `openpyxl>=3.1.2`)
- `school-management-system/config/settings.py` (Add new apps to `INSTALLED_APPS`, email backend config, DRF throttle config)
- `school-management-system/api/urls.py` (Include new routes)
- `school-management-system/api/permissions.py` (Add `MustChangePasswordCheck` and active school resolution)

### 2.3 Frontend Files (`Frontend/indoreedu-web`)
- `src/types/index.ts` (Add Wave 2 types: Organization, SetupStatus, ImportPreview, TeacherPermission, Syllabus)
- `src/lib/api/wave2.ts` (Typed API client for Wave 2)
- `src/app/admin/setup/page.tsx` (Setup Wizard checklist)
- `src/app/admin/import/page.tsx` (Upgraded import UI: Teachers & Students sub-tabs, template download, row errors, credentials download)
- `src/app/verify-email/page.tsx` (Email verification handler)
- `src/components/layout/CampusSwitcher.tsx` (Active campus switcher in AdminHeader)
- `src/components/admin/TeacherPermissionsModal.tsx` (Granular teacher permission toggles)
- `src/components/admin/ForceChangePasswordModal.tsx` (Mandatory password change prompt when `must_change_password=True`)

---

## 3. Migration Plan

New apps are created with dependencies on existing apps:

1. **`organizations`** (`0001_initial.py`):
   - Dependencies: `[('schools', '0001_initial'), ('accounts', '0001_initial')]`
2. **`credentials`** (`0001_initial.py`):
   - Dependencies: `[('accounts', '0001_initial')]`
3. **`teacher_assignments`** (`0001_initial.py`):
   - Dependencies: `[('schools', '0001_initial'), ('academics', '0001_initial'), ('accounts', '0001_initial')]`
4. **`syllabus`** (`0001_initial.py`):
   - Dependencies: `[('academics', '0001_initial')]`

Verification:
- `python manage.py makemigrations --check --dry-run` shows 0 changes for existing apps.
- `python manage.py migrate` applies the 4 new initial migrations cleanly.

---

## 4. API Contract

### 4.1 Organizations & Multi-Campus
- `POST /api/v1/auth/register-org/`
  - Permission: `AllowAny`, Throttled (5/hr)
  - Request: `{"organizationName": "...", "campusName": "...", "username": "...", "email": "...", "mobile": "...", "password": "..."}`
  - Generic Error: If email or username exists, returns `400 {"detail": "An account with these details could not be registered."}` (no user enumeration).
  - Response: `201 {"detail": "Organization registered. Please verify your email.", "organization": {...}, "school": {...}}`
- `GET /api/v1/auth/verify-email/?token=...`
  - Action: Hashes token with SHA-256, matches unused non-expired token, sets `SchoolOrganization.status = 'active'`, marks token used, logs in user.
- `GET /api/v1/organizations/campuses/`
  - Permission: `IsAuthenticated` (Org Owner/Admin)
  - Response: `[{"id": 1, "name": "Main Campus", "code": "MC-09", "status": "active", "isCurrent": true}]`
- `POST /api/v1/organizations/switch-campus/`
  - Permission: `IsAuthenticated`
  - Request: `{"schoolId": 2}`
  - Validation: Verifies school 2 belongs to user's Organization via `OrganizationMember(owner|admin)`. Returns 403 if not.
  - Action: Sets `request.session["active_school_id"] = 2`, logs `campus.switch` in `AuditLog`.
  - Response: Updated session payload.

### 4.2 Setup Wizard Checklist
- `GET /api/v1/setup-wizard/status/`
  - Permission: `IsPrincipalOrSuperuser`
  - Response:
    ```json
    {
      "schoolId": 1,
      "schoolName": "SGSITS Indore",
      "status": "pending",
      "overallProgress": 50,
      "checklist": {
        "academicYear": {"completed": true, "count": 1, "label": "Academic Year Configured"},
        "classes": {"completed": true, "count": 6, "label": "Classes & Sections Added"},
        "teachers": {"completed": false, "count": 0, "label": "Teachers Added"},
        "students": {"completed": false, "count": 0, "label": "Students Enrolled"}
      }
    }
    ```

### 4.3 Credentials & Security
- `POST /api/v1/credentials/reset-password/`
  - Permission: `IsPrincipalOrSuperuser`, Throttled (20/hr)
  - Request: `{"userId": 42}`
  - Action: Generates secure password, sets `UserSecurity.must_change_password = True`, logs `credentials.reset` in `AuditLog`.
  - Response: `{"temporaryPassword": "..."}`
- `POST /api/v1/auth/change-password/`
  - Permission: `IsAuthenticated`
  - Request: `{"oldPassword": "...", "newPassword": "..."}`
  - Action: Validates strength, updates password, clears `must_change_password = False`.
- **Must-Change-Password Enforcement**:
  - Middleware/Permission in `api/`: If `user.security.must_change_password == True`, any request other than `/auth/change-password/`, `/auth/logout/`, `/auth/me/`, `/auth/csrf/` is rejected with `403 {"detail": "You must change your temporary password before proceeding.", "code": "MUST_CHANGE_PASSWORD"}`.

### 4.4 Excel Import Engine
- `GET /api/v1/import/template/teachers/`
  - Permission: `IsPrincipalOrSuperuser`
  - Response: Streaming `.xlsx` file download
- `GET /api/v1/import/template/students/`
  - Permission: `IsPrincipalOrSuperuser`
  - Response: Streaming `.xlsx` file download
- `POST /api/v1/import/preview/`
  - Permission: `IsPrincipalOrSuperuser`, Throttled (10/min)
  - Request: `multipart/form-data` with `type` ('teacher' | 'student') and `file` (.xlsx, <= 5MB, <= 2000 rows)
  - Validation: Formula-injection sanitization, row-level checks, global uniqueness checks on `admission_number` / `employee_id`.
  - Action: Stores validated payload in Django cache (`cache.set(key, payload, timeout=1800)`), generates signed `importToken` containing `{"key": key, "user_id": user.id, "school_id": school.id}`.
  - Response: `{ "importToken": "...", "totalRows": 100, "validRows": 98, "errorRows": 2, "errors": [...], "preview": [...] }`
- `POST /api/v1/import/confirm/`
  - Permission: `IsPrincipalOrSuperuser`, Throttled (5/min)
  - Request: `{"importToken": "..."}`
  - Guard: If `school.organization_membership.status == 'pending'`, reject with `403 {"detail": "School email verification is pending. Verify your email to complete import."}`.
  - Validation: Unsigns token, verifies `user_id == request.user.id` and `school_id == active_school.id`, retrieves cached payload.
  - Execution: In atomic transaction:
    - Creates records.
    - Students: deduplicate `Guardian` by `(school, mobile)`, set `link_status='approved'`. Parent `User` created if not exists with `username=normalized_10_digit_mobile`.
    - Creates `UserSecurity(must_change_password=True)`.
    - Logs `import.teachers` or `import.students` in `AuditLog`.
    - Builds credentials workbook in memory via `openpyxl`.
  - Response: Direct binary stream of `.xlsx` credentials file:
    - `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
    - `Content-Disposition: attachment; filename="credentials_<type>_<timestamp>.xlsx"`
    - `Cache-Control: no-store`

### 4.5 Teacher Permissions & Assignments
- Permission keys: `attendance_backdate`, `manage_syllabus`, `publish_notices`, `view_student_contacts`.
- `GET /api/v1/teachers/<id>/permissions/`
- `POST /api/v1/teachers/<id>/permissions/`
  - Request: `{"permissionKey": "attendance_backdate", "granted": true}`
  - Validation: Reject unknown keys with `400 {"detail": "Invalid permission key"}`.
  - Action: Creates or deletes `TeacherPermission`, logs `permission.grant` or `permission.revoke`.
- `GET/POST /api/v1/classes/<id>/subject-teachers/`
  - Maps `(school_class, subject)` -> `teacher`.

### 4.6 Syllabus Management
- `GET /api/v1/subjects/<id>/syllabus/`
- `POST /api/v1/subjects/<id>/units/` (Title, unit number, description)
- `POST /api/v1/units/<id>/topics/` (Title, topic number, description)
- `PATCH /api/v1/topics/<id>/status/`
  - Permission: Principal or Teacher assigned to that subject or having `manage_syllabus` permission.
  - Request: `{"status": "completed"}`

---

## 5. Test Plan

### `organizations`
1. `test_register_org_creates_org_school_principal_and_pending_status`
2. `test_register_org_duplicate_email_or_username_returns_generic_error`
3. `test_verify_email_hashes_token_and_activates_school`
4. `test_campus_switch_verifies_org_membership_on_every_request`
5. `test_campus_switch_rejects_unowned_school`
6. `test_removed_member_loses_access_immediately_on_next_request`

### `credentials`
7. `test_username_generator_produces_schoolcode_id_format`
8. `test_random_password_generator_meets_django_complexity`
9. `test_must_change_password_blocks_normal_endpoints_until_changed`
10. `test_principal_password_reset_creates_user_security_and_audit_log`
11. `test_plaintext_passwords_never_persisted`

### `importers`
12. `test_formula_injection_sanitization`
13. `test_file_size_limit_5mb_and_row_limit_2000`
14. `test_duplicate_admission_number_at_another_school_produces_row_error`
15. `test_pending_school_blocked_from_import_confirm`
16. `test_student_import_deduplicates_guardians_and_reuses_parent_user_by_mobile_username`
17. `test_import_confirm_rejects_token_from_another_user_or_school`
18. `test_import_confirm_returns_direct_binary_xlsx_with_no_store_header`

### `teacher_assignments`
19. `test_permission_keys_whitelist_rejects_unknown_keys`
20. `test_grant_and_revoke_permissions_log_audit_actions`
21. `test_teacher_with_attendance_backdate_can_edit_past_attendance`
22. `test_class_subject_teacher_enforces_one_teacher_per_subject`

### `syllabus`
23. `test_unit_and_topic_ordering_and_uniqueness`
24. `test_assigned_teacher_can_update_topic_status`
25. `test_unassigned_teacher_cannot_update_topic_without_manage_syllabus_permission`

---

## 6. Frontend Plan

1. **Setup Wizard (`/admin/setup`)**:
   - Visual progress card with step checklist.
   - Shows "Pending Email Verification" notice when applicable.
2. **Import Hub (`/admin/import`)**:
   - Sub-tabs for "Teachers" and "Students".
   - Official `.xlsx` template download buttons.
   - 3-step UI: Upload -> Preview with Row-level Error Table -> Confirm.
   - Direct automatic file download trigger for credentials sheet on confirm.
3. **Multi-Campus Switcher (`CampusSwitcher.tsx`)**:
   - Embedded in `AdminHeader`. Displays current active campus and dropdown of campuses owned by the organization.
4. **Teacher Permission Modal (`TeacherPermissionsModal.tsx`)**:
   - Accessible from `/admin/teachers`. Toggles for the 4 permission keys.
5. **Syllabus Tree View (`/admin/syllabus`)**:
   - Expandable tree view for Units and Topics with status update controls.
6. **Force Change Password Modal (`ForceChangePasswordModal.tsx`)**:
   - Automatically intercepts users flagged with `must_change_password` and requires a new password before navigating further.

---

## 7. Implementation Order

1. **Step 0**: Update `requirements.txt` with `openpyxl>=3.1.2` and install in `.venv`.
2. **Step 1**: Implement `organizations` app (multi-campus switching, email verification token hashing, generic registration errors, tests).
3. **Step 2**: Implement `credentials` app (`UserSecurity`, username/password generation, `must_change_password` enforcement, password reset service, tests).
4. **Step 3**: Implement `importers` app (openpyxl templates, formula sanitizer, dry-run validator with cache-backed token, confirm flow with guardian deduplication and direct binary streaming, tests).
5. **Step 4**: Implement `teacher_assignments` app (`TeacherPermission` whitelist, `ClassSubjectTeacher` mapping, tests).
6. **Step 5**: Implement `syllabus` app (`Unit`, `Topic`, status update service, tests).
7. **Step 6**: Implement Frontend interfaces (`/admin/setup`, `/admin/import`, `CampusSwitcher`, permissions modal, syllabus manager).
8. **Step 7**: End-to-end verification (`makemigrations --check`, full test suite, frontend build).
