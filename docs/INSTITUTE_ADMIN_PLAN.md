# Institute Admin Feature Set Plan & Audit

This plan audits the existing Django backend architecture for the Institute Admin (admin, principal, superuser) and proposes a clean, additive API design for `indoreedu-web` under the zero-model and additive-only constraints.

---

## 1. Existing Backend Audit

### 1.1 Roles & Tenant Scoping
- **Roles**: `User.ROLE_CHOICES = ('admin', 'principal', 'teacher', 'student', 'parent')`. Superusers have `is_superuser=True`.
- **Principal vs Admin**:
  - `admin` / `is_superuser`: Global system scope. Can view/create/edit/delete all schools, principals, teachers, classes, students.
  - `principal`: Scoped strictly to one institute via `School.principal` (`OneToOneField(User, related_name='principal_school')`).
- **School <-> Principal Link**:
  - `School.principal` is a 1-to-1 field to `User`. When a principal is created in `schools/views.py:principal_create`, `school.principal = user; school.save()`.

### 1.2 Existing Admin / Principal Feature Matrix
| Feature | URL Name | Allowed Roles | Form & Validations | Side Effects | Delete / Cascades |
|---|---|---|---|---|---|
| School List / CRUD | `school_list`, `school_create`, `school_update`, `school_delete` | Superuser only | `SchoolForm`: name, code (unique), address, city, phone, email, principal | Assigns principal to school | `CASCADE` on classes, teachers, students, subjects. `SET_NULL` on principal user. |
| Principal Management | `principal_list`, `principal_create`, `principal_delete` | Superuser only | `PrincipalForm`: user fields + password match + `school` selector | Creates `User(role='principal')` + links to `school.principal` | `School.objects.filter(principal=p).update(principal=None); principal.delete()` |
| Teacher CRUD | `teacher_list`, `teacher_create`, `teacher_delete` | Superuser or Principal (scoped to `request.user.principal_school`) | `TeacherForm`: name, username (unique check), email, mobile, password match, employee_id (unique), qualification, joining_date, designation | Creates `User(role='teacher')` + `Teacher` record linked to school | Deletes `teacher` and its linked `user` (`CASCADE`) |
| Class CRUD | `class_list`, `class_create`, `class_delete` | Superuser or Principal (scoped to `request.user.principal_school`) | `SchoolClassForm`: name, section, `class_teacher` (filtered by school) | None | `CASCADE` from School; `SET_NULL` on Teacher and Students |
| Student CRUD | `student_list`, `student_create`, `student_delete` | Superuser or Principal (scoped to `request.user.principal_school`) | `StudentForm`: user fields + student fields (admission_number unique, class_section, parents, contact, DOB, gender) | Creates `User(role='student', password=form.password)` + `Student` record | Deletes `student` and its linked `user` (`CASCADE`) |
| Excel Import | `import_excel`, `confirm_import` | Superuser only | `ExcelUploadForm`: school choice + file (`.csv`, `.xlsx`, `.xls`) | Generates `import_token` via `signing.dumps` in temp file, previews 10 rows. On confirm: creates students, classes on-the-fly (`get_or_create`), generated usernames (`{school.code}_{admission_number}`) with default password `"Student@123"` | None (creates records atomically inside `transaction.atomic()`) |

---

## 2. Proposed Additive API Endpoints

All endpoints will be additive inside the `api` app (`api/views_admin.py` or `api/views.py`):

| Resource | Method | Path | Permission | Scoping Rule | Writable Fields (Allow-list) | Notes |
|---|---|---|---|---|---|---|
| Schools | `GET` | `/api/v1/admin/schools/` | `IsAdminUser \| IsPrincipal` | Superuser: all; Principal: own school | None (read-only list) | Supports search & city filters |
| Schools | `POST` | `/api/v1/admin/schools/` | `IsSuperUser` | Global | `name`, `code`, `address`, `city`, `phone`, `email` | Reuses validation logic |
| Schools | `PATCH/PUT` | `/api/v1/admin/schools/:id/` | `IsSuperUser \| (IsPrincipal & OwnSchool)` | Own school only for principal | `address`, `city`, `phone`, `email` (`name`, `code` superuser only) | Zero cross-tenant leaks |
| Classes | `GET` | `/api/v1/admin/classes/` | `IsAdminUser \| IsPrincipal` | Principal: own school; Superuser: all or `?school=id` | None | Lists sections and class teacher |
| Classes | `POST` | `/api/v1/admin/classes/` | `IsAdminUser \| IsPrincipal` | Forces `school = principal.school` | `name`, `section`, `class_teacher_id` | Class teacher must belong to same school |
| Classes | `DELETE` | `/api/v1/admin/classes/:id/` | `IsAdminUser \| IsPrincipal` | Own school only | None | Checks dependent students |
| Teachers | `GET` | `/api/v1/admin/teachers/` | `IsAdminUser \| IsPrincipal` | Principal: own school; Superuser: all or `?school=id` | None | Includes employeeId, user profile |
| Teachers | `POST` | `/api/v1/admin/teachers/` | `IsAdminUser \| IsPrincipal` | Forces `school = principal.school` | `first_name`, `last_name`, `username`, `email`, `mobile`, `password`, `employee_id`, `qualification`, `joining_date`, `designation` | Atomic transaction: creates User + Teacher |
| Teachers | `DELETE` | `/api/v1/admin/teachers/:id/` | `IsAdminUser \| IsPrincipal` | Own school only | None | Atomic deletion of Teacher + User |
| Students | `GET` | `/api/v1/admin/students/` | `IsAdminUser \| IsPrincipal` | Principal: own school; Superuser: all or `?school=id` | None | Paginated (`page`, `page_size`, `search`, `class_id`) |
| Students | `POST` | `/api/v1/admin/students/` | `IsAdminUser \| IsPrincipal` | Forces `school = principal.school` | `first_name`, `last_name`, `username`, `email`, `mobile`, `password`, `admission_number`, `class_section_id`, `gender`, `date_of_birth`, `address`, `father_name`, `mother_name` | Atomic transaction: creates User + Student |
| Students | `DELETE` | `/api/v1/admin/students/:id/` | `IsAdminUser \| IsPrincipal` | Own school only | None | Atomic deletion of Student + User |
| Import Preview | `POST` | `/api/v1/admin/import/preview/` | `IsAdminUser \| IsPrincipal` | Forces school to principal's school | `file` (multipart/form-data) | Reuses `read_uploaded_file`, returns columns, row count & preview |
| Import Confirm | `POST` | `/api/v1/admin/import/confirm/` | `IsAdminUser \| IsPrincipal` | Forces school to principal's school | `import_token` | Executes atomic import, returns `{ imported, duplicate, errors }` |

---

## 3. Code Reuse vs. Reimplementation in `api`

### Reused Without Modifying Existing Code:
- `schools.models.School`, `academics.models.{Teacher, Student, SchoolClass, Subject}`, `accounts.models.User`.
- `imports.views.{read_uploaded_file, clean_value, split_name, normalize_column_name, convert_date, convert_fee}`: Pure file processing helpers can be imported directly into the API import handler.
- Django authentication helpers: `authenticate`, `login`, `logout`, `validate_password`.

### Reimplemented in `api`:
- DRF Serializers: `AdminTeacherSerializer`, `AdminStudentSerializer`, `AdminClassSerializer`, `AdminSchoolSerializer` (needed for JSON serialization, custom validation errors, camelCase formatting).
- Permission Classes: `IsInstituteAdmin` (checks `request.user.is_superuser or request.user.role in ['admin', 'principal']`).
- Scoped Queryset Helpers: helper function `get_scoped_school(request)` returning the bound `School` instance or 403.
- Transactional Creation Routines: DRF-compatible `create_teacher` and `create_student` that handle `User.objects.create_user` and model instance creation atomically.

---

## 4. Architectural & Security Risks
1. **Cross-School Tenant Leaks**: Principals must NEVER pass `school_id` in request payloads; `school` must always be derived from `request.user.principal_school`.
2. **Mass-Assignment**: Strict field allow-lists on write endpoints; prevent arbitrary assignment of `role`, `is_superuser`, `is_staff`, or `school`.
3. **User Account Side Effects**: Deleting a student/teacher must cleanly delete the linked `User` without leaving orphan auth accounts; creating student/teacher must validate password strength and handle username collisions gracefully.
4. **Excel Import Performance & Memory**: Large `.xlsx` files (>5,000 rows) can spike server memory and time out HTTP requests. Must set maximum upload file size (e.g. 5 MB) and maximum rows (e.g. 2,000 rows per batch) with chunked parsing.
5. **Pagination**: `Student.objects.all()` in institutes with thousands of pupils must be paginated via DRF `PageNumberPagination` to avoid crashing client and server.
