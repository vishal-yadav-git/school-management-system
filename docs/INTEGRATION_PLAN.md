# IndoreEdu Integration Plan (Phase 0 Audit)

## Executive Summary
This document provides the complete Phase 0 audit of the existing Django backend (`school-management-system`) and the Stitch design export screens (`Frontend/`). It details the backend model and field inventory, maps existing versus missing data across all screens, defines the proposed additive API endpoints, lists all planned file changes, and highlights technical risks and mitigations.

---

## 1. Backend Architecture & Model Inventory

The existing backend is built with **Django 6.1.1** on **Python 3.14** using SQLite (`db.sqlite3`).
All authentication is standard Django session-based authentication (`django.contrib.sessions`, `django.contrib.auth`).

### 1.1 Model & Field Inventory

| App | Model | Existing Fields | Relationships & Reverse Accessors |
| :--- | :--- | :--- | :--- |
| **accounts** | `User` (AbstractUser) | `id`, `username`, `first_name`, `last_name`, `email`, `is_staff`, `is_active`, `is_superuser`, `date_joined`, `role` (choices: `admin`, `principal`, `teacher`, `student`, `parent`, default: `student`), `mobile` (CharField, max 15, blank) | `principal_school` (OneToOne from School), `teacher_profile` (OneToOne from Teacher), `student_profile` (OneToOne from Student) |
| **schools** | `School` | `id`, `name` (max 200), `code` (max 20, unique), `address` (text), `city` (max 100), `phone` (max 15, blank), `email` (blank), `principal` (OneToOne to User, nullable), `created_at` (DateTimeField) | `teachers` (FK from Teacher), `classes` (FK from SchoolClass), `students` (FK from Student), `subjects` (FK from Subject) |
| **academics** | `Teacher` | `id`, `user` (OneToOne to User), `school` (FK to School), `employee_id` (max 50, unique), `qualification` (max 200, blank), `joining_date` (DateField, nullable), `designation` (default: 'Teacher') | `class_teacher_for` (FK from SchoolClass) |
| **academics** | `SchoolClass` | `id`, `school` (FK to School), `name` (max 50), `section` (max 10), `class_teacher` (FK to Teacher, nullable) | `students` (FK from Student) |
| **academics** | `Student` | `id`, `user` (OneToOne to User), `school` (FK to School), `class_section` (FK to SchoolClass, nullable), `admission_number` (max 50, unique), `date_of_birth` (DateField, nullable), `gender` (choices: Male, Female, Other), `address` (text, blank), `admission_date` (DateField, auto_now_add) | None |
| **academics** | `Subject` | `id`, `school` (FK to School), `name` (max 100), `code` (max 30) | None |
| **core** | *None* | No models defined | Contains dashboard routing views |
| **imports** | *None* | No models defined | Contains Excel / CSV import routines |

### 1.2 Missing Backend Capabilities (Must Remain Mock)
The following concepts exist in the Stitch designs but **do NOT exist** in the Django models:
1. **Attendance / Biometric Logs**: No `Attendance` or `AttendanceRecord` model exists.
2. **Fees, Installments & Transactions**: No `Fee`, `FeeReceipt`, or `FeePayment` model exists.
3. **Exams, Marks & Report Cards**: No `Exam`, `Grade`, or `Marksheet` model exists.
4. **Notices, Circulars & News**: No `Notice`, `News`, or `Circular` model exists.
5. **Parent-to-Student Relationship**: While `User.role == 'parent'` exists, there is no Parent profile model and no foreign key or link connecting a parent to any student(s).
6. **Detailed Institute/College Profile Data**: No accreditation fields (`NAAC`, `NIRF`, `AICTE`, `Autonomous`), cutoffs (`JEE Main`, `CET`), campus photos, reviews/ratings, or fee range fields on `School`.
7. **Phone OTP Service**: Backend uses standard username + password authentication (`authenticate(request, username=..., password=...)`).

---

## 2. Screen Data Mapping: Real vs. Mock Breakdown

| Stitch Screen & Route | Screen Component / Section | Backend Support | Status | Data Source Details |
| :--- | :--- | :--- | :--- | :--- |
| **indoreedu_home** (`/`) | Header & Navigation Bar | N/A (Static) | **REAL / STATIC** | Shared navigation and category links. |
| | Hero Search & Category Select | Client-side filter | **MOCK** | Filters list in-memory; no search backend index. |
| | Hero ERP Promo Card | Static promotional content | **MOCK** | Stitch export content. |
| | Indore Academic Radar (News) | None | **MOCK** | Mock news feed (`src/lib/mock/news.ts`). |
| | Top Institutes in Indore | Partially supported | **REAL / MOCK** | **Real**: School name, address, city from `GET /api/v1/schools/`.<br>**Mock**: Ratings (4.7-4.9), review counts, fee ranges, badges (Verified, Popular, Top Engg), brochure links. |
| | Institutional OS 6-Feature Grid | Static product features | **MOCK** | Stitch marketing grid. |
| | Mobile App Download & QR Code | Static marketing content | **MOCK** | Stitch marketing section. |
| | Footer & Locality Directory | Static directory links | **REAL / STATIC** | Standard links matching Stitch design. |
| **indoreedu_colleges_in_indore** (`/institutes`) | Breadcrumb & Header Count | Static / Count from API | **REAL / MOCK** | Dynamic count if schools exist, fallback to 184 verified. |
| | Filter Sidebar (Type, Affiliation, Locality, Fees, Rating, Facilities) | None | **MOCK** | Client-side interactive filter state based on mock tags. |
| | College Directory Cards | Partially supported | **REAL / MOCK** | **Real**: School name, code, address, city.<br>**Mock**: Monograms, NAAC A++ / NIRF badges, JEE cutoff percentiles, placement packages, tuition fee ranges, application links. |
| | Free Student Helpline Banner | Static banner | **MOCK** | Helpline phone and callback modal. |
| **indoreedu_sgsits_indore_profile** (`/institutes/[id]`) | Header Banner & Badge Strip | Partially supported | **REAL / MOCK** | **Real**: School name, code, address, city from `GET /api/v1/schools/<id>/`.<br>**Mock**: Highest CTC ₹44.5 LPA, Estd 1952, NIRF 151-200, DTE Code 0801, photo banner. |
| | Overview & About Campus | None | **MOCK** | Stitch narrative text. |
| | Courses & Fees (14 Programs) | None | **MOCK** | Program list, duration, intake seats, annual fees. |
| | Admissions & Cutoffs Table | None | **MOCK** | DTE MP Round cutoffs & closing ranks. |
| | Campus Facilities Checklist | None | **MOCK** | Smart labs, hostels, sports complex badges. |
| | Reviews & Rating Breakdown | None | **MOCK** | 890 reviews, 4.7 star breakdown. |
| **indoreedu_login** (`/login`) | Role Selector Tabs (Admin, Teacher, Parent, Student) | `User.ROLE_CHOICES` | **REAL** | Selects user context and dictates dashboard destination. |
| | Sign-in Form (Username / Password) | `accounts.views.login_view` | **REAL** | `POST /api/v1/auth/login/` with session cookie and CSRF protection. Authenticates against Django `User`. |
| | Role-Based Post-Login Routing | `core.views.dashboard` | **REAL** | Superuser $\rightarrow$ `/admin`<br>Principal $\rightarrow$ `/admin`<br>Teacher $\rightarrow$ `/teacher/attendance`<br>Parent $\rightarrow$ `/parent`<br>Student $\rightarrow$ `/institutes` |
| | "Get Verification OTP" button | None | **MOCK** | Fallback visual matching Stitch; primary submit authenticates credentials. |
| | Google Workspace SSO | None | **MOCK** | Visual SSO button per Stitch layout. |
| **indoreedu_admin_dashboard** (`/admin`) | Sidebar Navigation & User Info | `accounts.User`, `School` | **REAL** | Current admin/principal name, school name, role badge. |
| | KPI 1: Total Students Enrolled | `Student.objects.filter(...)` | **REAL** | Count of enrolled students (scoped to school for principal). |
| | KPI 2: Faculty & Staff | `Teacher.objects.filter(...)` | **REAL** | Count of teachers (scoped to school for principal). |
| | KPI 3: Present Today (94.6%) | None | **MOCK** | Mock attendance percentage tile. |
| | KPI 4: Fees Collected (₹3.84 Cr) | None | **MOCK** | Mock fees progress tile. |
| | Weekly Attendance Trends Chart | None | **MOCK** | Mock day-by-day bar chart. |
| | Fee Collection Breakdown | None | **MOCK** | Mock department-level collection bars. |
| | Recent Campus Activity Feed | None | **MOCK** | Mock activity timeline items. |
| | Notices & Circulars List | None | **MOCK** | Mock circular items with tags. |
| **indoreedu_teacher_attendance** (`/teacher/attendance`) | Teacher Profile Header | `Teacher`, `User`, `School` | **REAL** | Teacher name, designation, school, department. |
| | Assigned Class / Batch | `SchoolClass` | **REAL** | Class and section assigned to teacher. |
| | Student Roster List | `Student.objects.filter(...)` | **REAL / MOCK** | **Real**: If students exist in teacher's class.<br>**Mock**: Fallback to 12 mock students if DB class has no students. |
| | Present / Absent Toggles & Turnout Math | Client-side logic | **REAL** | Fully functional interactive state matching Stitch counter logic. |
| | Submit Attendance Action | None | **MOCK** | Shows success confirmation dialog ("Session locked & dispatched to parents"). |
| **indoreedu_parent_mobile_home** (`/parent`) | Greeting & Parent Profile | `accounts.User` | **REAL** | Logged-in parent full name from session. |
| | Switch Student Profile Carousel | None | **MOCK** | Mock children (Aarav, Ananya) switcher. |
| | Daily Attendance Status & Bus Route | None | **MOCK** | Mock biometric timestamp and bus route status. |
| | Urgent Fee Due Card (₹18,500) | None | **MOCK** | Mock invoice & payment CTA. |
| | Mid-Term Examination Result Card | None | **MOCK** | Mock subject marks breakdown. |
| | School Notices & Circulars | None | **MOCK** | Mock notices list. |
| | Campus Helpline Quick Dial | Static / Phone | **REAL / STATIC**| Dialable contact links. |

---

## 3. Proposed Backend API Endpoints (Additive Only)

All endpoints will be placed under the prefix `/api/v1/` in a new Django app named `api`.
Authentication mechanism: Django Session Authentication (`SessionAuthentication`) with CSRF verification.

### 3.1 Authentication & Session
- `GET /api/v1/auth/csrf/`
  - **Purpose**: Sets and returns the CSRF token for the frontend client.
  - **Permissions**: `AllowAny`
  - **Response**: `{"csrfToken": "..."}`
- `POST /api/v1/auth/login/`
  - **Purpose**: Authenticates user via `username` and `password`, establishes a Django session cookie.
  - **Permissions**: `AllowAny`
  - **Payload**: `{"username": "...", "password": "..."}`
  - **Response**: `{"user": {"id": 1, "username": "...", "firstName": "...", "lastName": "...", "role": "admin", "isSuperuser": false}, "school": {"id": 1, "name": "...", "code": "..."}, "redirectUrl": "/admin"}`
- `POST /api/v1/auth/logout/`
  - **Purpose**: Clears Django session.
  - **Permissions**: `IsAuthenticated`
  - **Response**: `{"detail": "Logged out successfully"}`
- `GET /api/v1/auth/me/`
  - **Purpose**: Returns the currently authenticated user, role, permissions, and associated school context.
  - **Permissions**: `IsAuthenticated`
  - **Response**: User object with profile metadata and school context.

### 3.2 Schools (Institutes)
- `GET /api/v1/schools/`
  - **Purpose**: Returns list of schools (for public home and institutes directory). Supports optional query params `?search=` and `?city=`.
  - **Permissions**: `AllowAny`
  - **Response**: `[{"id": 1, "name": "...", "code": "...", "address": "...", "city": "Indore", "phone": "...", "email": "..."}]`
- `GET /api/v1/schools/<int:pk>/`
  - **Purpose**: Returns single school details.
  - **Permissions**: `AllowAny`
  - **Response**: Detailed school object.

### 3.3 Dashboard Metrics (Scoping & Security)
- `GET /api/v1/dashboard/stats/`
  - **Purpose**: Returns overview counts mirroring `core/views.py`.
  - **Permissions**: `IsAuthenticated`
  - **Scoping**:
    - **Superuser (`is_superuser=True`)**:
      - `totalSchools`: `School.objects.count()`
      - `totalPrincipals`: `User.objects.filter(role='principal').count()`
      - `totalTeachers`: `Teacher.objects.count()`
      - `totalStudents`: `Student.objects.count()`
      - `totalClasses`: `SchoolClass.objects.count()`
      - `totalSubjects`: `Subject.objects.count()`
    - **Principal (`role='principal'`)**:
      - Scoped to `school = request.user.principal_school`
      - `totalTeachers`: `Teacher.objects.filter(school=school).count()`
      - `totalStudents`: `Student.objects.filter(school=school).count()`
      - `totalClasses`: `SchoolClass.objects.filter(school=school).count()`
      - `totalSubjects`: `Subject.objects.filter(school=school).count()`

### 3.4 Academics (Scoped Lists)
- `GET /api/v1/academics/classes/`
  - **Purpose**: Lists classes for the active school context.
  - **Permissions**: `IsAuthenticated` (Principal or Superuser).
- `GET /api/v1/academics/teachers/`
  - **Purpose**: Lists teachers for the active school context.
  - **Permissions**: `IsAuthenticated` (Principal or Superuser).
- `GET /api/v1/academics/students/`
  - **Purpose**: Lists students for the active school context.
  - **Permissions**: `IsAuthenticated` (Principal or Superuser).
- `GET /api/v1/teacher/my-students/`
  - **Purpose**: For logged-in teacher, returns students in the classes they are designated as class teacher (`request.user.teacher_profile.class_teacher_for.all()`).
  - **Permissions**: `IsAuthenticated` (`role == 'teacher'`).

---

## 4. Exact List of Backend Files to Add / Edit

### 4.1 New Files to Add (Additive Only in `api/`)
1. `school-management-system/api/__init__.py`
2. `school-management-system/api/apps.py`
3. `school-management-system/api/permissions.py` — enforces role and school tenant isolation.
4. `school-management-system/api/serializers.py` — read-only DRF serializers for User, School, Teacher, SchoolClass, Student, Subject.
5. `school-management-system/api/views.py` — views for auth, schools, academics, dashboard.
6. `school-management-system/api/urls.py` — URL patterns under `/api/v1/`.

### 4.2 Existing Backend Files to Edit (Minimal & Strictly Compliant)
1. `school-management-system/config/settings.py`:
   - Add `'rest_framework'` and `'api'` to `INSTALLED_APPS`.
   - Add `REST_FRAMEWORK` dictionary (SessionAuthentication, permissions).
   - Add `CSRF_TRUSTED_ORIGINS = ['http://localhost:3000', 'http://127.0.0.1:3000']`.
   - Add `CORS_ALLOWED_ORIGINS = ['http://localhost:3000', 'http://127.0.0.1:3000']` and `CORS_ALLOW_CREDENTIALS = True` (if django-cors-headers is active).
2. `school-management-system/config/urls.py`:
   - Add ONE line: `path('api/v1/', include('api.urls')),`
3. `school-management-system/requirements.txt`:
   - Add `djangorestframework` and `django-cors-headers` (and install into `venv`).

---

## 5. Frontend Architecture Plan (`Frontend/indoreedu-web/`)

### 5.1 Technology Stack
- **Framework**: Next.js 15+ (App Router), React 19, TypeScript
- **Styling**: Tailwind CSS configured with exact tokens from `DESIGN.md`
- **Icons**: Material Symbols Outlined (loaded via Google Fonts / SVG)
- **Fonts**: Plus Jakarta Sans (loaded via `next/font/google`)
- **Networking**: Next.js API rewrite proxy (`/api/:path* -> http://127.0.0.1:8000/api/:path*`) to maintain same-origin cookies and eliminate CORS complications.

### 5.2 Theme Tokens (`tailwind.config.ts`)
Converted strictly from `DESIGN.md`:
- **Colors**:
  - `surface`: `#fcf8ff`
  - `surface-dim`: `#dad6f8`
  - `surface-bright`: `#fcf8ff`
  - `surface-container-lowest`: `#ffffff`
  - `surface-container-low`: `#f6f2ff`
  - `surface-container`: `#efebff`
  - `surface-container-high`: `#e9e5ff`
  - `surface-container-highest`: `#e3dfff`
  - `on-surface`: `#1a1932`
  - `on-surface-variant`: `#474553`
  - `outline`: `#787585`
  - `outline-variant`: `#c9c4d5`
  - `primary`: `#4330ab`
  - `primary-container`: `#5b4bc4`
  - `on-primary`: `#ffffff`
  - `on-primary-container`: `#dad3ff`
  - `secondary`: `#5d54a1`
  - `tertiary`: `#822700`
  - `tertiary-container`: `#F26B3A` / `#a93705`
  - `inverse-surface`: `#2A1F6B` / `#2f2e48`
  - `inverse-on-surface`: `#f2efff`
- **Border Radii**: `sm` (0.25rem), `DEFAULT` (0.5rem), `md` (0.75rem), `lg` (1rem), `xl` (1.5rem), `full` (9999px)
- **Typography**: Complete `Plus Jakarta Sans` scale for `display-lg`, `headline-xl`, `headline-lg`, `headline-md`, `headline-sm`, `body-lg`, `body-md`, `body-sm`, `label-lg`, `label-md`, `label-sm`.

### 5.3 Data Layer Structure
```
Frontend/indoreedu-web/src/
  ├── lib/
  │   ├── api/
  │   │   ├── client.ts             # fetch wrapper (credentials: 'include', X-CSRFToken header)
  │   │   ├── auth.ts               # login, logout, getMe, getCsrf
  │   │   ├── schools.ts            # getSchools, getSchoolById
  │   │   ├── academics.ts          # getClasses, getStudents, getTeachers, getTeacherStudents
  │   │   └── dashboard.ts          # getDashboardStats
  │   ├── mock/
  │   │   ├── schools.ts            # SGSITS, Daly College, Allen, MGM, IIPS dummy data
  │   │   ├── news.ts               # MPBSE timetable, DAVV CET, IIT Indore news
  │   │   ├── attendance.ts         # 12 students roster with Aarav Sharma, Priyanshu Patel, etc.
  │   │   ├── parent.ts             # Aarav & Ananya parent data, fees, results, bus route
  │   │   └── adminDashboard.ts     # Attendance bar charts, fee reconciliation, activity logs
  │   └── config/
  │       └── dataSources.ts        # Flags per resource: { auth: "api", schools: "api", dashboard: "api", attendance: "mock", parent: "mock" }
```

---

## 6. Risks & Mitigations

1. **Risk:** `Student.objects.create` in existing `academics/views.py` has invalid parameter calls (`father_name`, `fees`, etc.) not in `Student` model.
   - **Mitigation:** Under Rule 1 we do not touch existing `academics/views.py`. Our new `api` serializers and views will strictly validate and serialize only the real model fields present in Django migration `0001_initial.py`.
2. **Risk:** Login screen in Stitch showcases phone number + OTP, but Django backend supports username + password.
   - **Mitigation:** The Stitch screen already includes an alternative section ("Or sign in with Password / SSO"). We will support clean username/password credential authentication that connects to Django's session login, with the role selector tabs dynamically updating the form hint and redirecting on success.
3. **Risk:** Cross-Origin session cookies blocked by browsers when frontend is on `localhost:3000` and Django is on `127.0.0.1:8000`.
   - **Mitigation:** A Next.js rewrite proxy in `next.config.ts` (`/api/:path* -> http://127.0.0.1:8000/api/:path*`) ensures that all API calls originate from `http://localhost:3000`. Cookies remain completely first-party/same-origin.
4. **Risk:** Database changes or unintended migrations.
   - **Mitigation:** The new `api` app will have **zero models**. Running `python manage.py makemigrations --check --dry-run` will consistently report "No changes detected".
5. **Risk:** Initial database is nearly empty (0 schools, 0 teachers, 0 classes).
   - **Mitigation:** The data layer gracefully combines real API response with fallback mock values when lists are empty, ensuring that every Stitch screen looks complete and pixel-faithful immediately.

---

## Phase 0 Sign-Off Request
This plan conforms to all hard rules and constraints. Awaiting user approval to proceed to **Phase 1 - Foundation** (Scaffolding Next.js, Tailwind tokens, fonts, shared components, and data layer skeleton).
