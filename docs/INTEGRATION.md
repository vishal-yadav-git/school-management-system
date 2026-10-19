# IndoreEdu System Integration Guide

This document describes how the Django backend (`school-management-system/`) and the Next.js frontend (`Frontend/indoreedu-web/`) integrate, how to run them on Windows, the exact data sources per route, how to transition mock features to real backend endpoints, and known limitations.

---

## 1. How to Run on Windows

### Prerequisites
- **Python**: Python 3.14 (in `school-management-system/venv/`)
- **Node.js**: v18+ (tested with Next.js 16 / React 19)
- **PowerShell**: Windows PowerShell

---

### Step 1: Run Django Backend (Port 8000)

Open a PowerShell terminal:
```powershell
cd "D:\pintu\My Projects\School Management System\school-management-system\school-management-system"
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```
- Server URL: `http://127.0.0.1:8000/`
- API Root: `http://127.0.0.1:8000/api/v1/`

---

### Step 2: Configure & Run Next.js Frontend (Port 3000)

Open a second PowerShell terminal:
```powershell
cd "D:\pintu\My Projects\School Management System\school-management-system\Frontend\indoreedu-web"
```

Verify or create `.env.local`:
```ini
DJANGO_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_SHOW_SAMPLE_TAGS=true
```

Run the development server:
```powershell
npm run dev
```
- Frontend Application URL: `http://localhost:3000/`

> **Note**: Next.js automatically rewrites `/api/:path*` to `http://127.0.0.1:8000/api/:path*` through `next.config.ts`, handling session cookies and CORS transparently without third-party CORS middleware.

---

## 2. Next.js Routes and Data Mapping

| Route | UI Block / Section | Data Status | API Endpoint / Fallback | dataSources.ts Flag |
|---|---|---|---|---|
| `/` | Hero section | REAL (meta) / MOCK (tags) | Static Stitch markup | `STATIC` |
| `/` | Indore Academic Radar | MOCK | `MOCK_ACADEMIC_NEWS` | `USE_MOCK_NEWS` |
| `/` | Top Institutes Grid | REAL (core) / MOCK (meta) | `GET /api/v1/schools/` (enriched with `MOCK_SCHOOLS`) | `USE_MOCK_SCHOOLS` |
| `/` | IndoreEdu OS Features | MOCK | Static Stitch markup | `STATIC` |
| `/` | Mobile App Showcase | MOCK | Static Stitch markup | `STATIC` |
| `/institutes` | Filter Sidebar | MOCK | Static filters | `STATIC` |
| `/institutes` | Colleges Directory List | REAL (core) / MOCK (meta) | `GET /api/v1/schools/` (enriched with `EXTENDED_COLLEGES`) | `USE_MOCK_SCHOOLS` |
| `/institutes/[id]` | Profile Header & Monogram | REAL (core) / MOCK (meta) | `GET /api/v1/schools/<id>/` | `USE_MOCK_SCHOOLS` |
| `/institutes/[id]` | Programs & Cutoffs | MOCK | Static table | `USE_MOCK_PROGRAMS` |
| `/institutes/[id]` | Campus Facilities & Reviews | MOCK | Static highlights | `STATIC` |
| `/institutes/[id]` | Enquire Now Form | MOCK | Client state (lead capture form) | `STATIC` |
| `/login` | Sign-in Form | REAL | `POST /api/v1/auth/login/` + `GET /api/v1/auth/csrf/` | `dataSources.auth: "api"` |
| `/register` | Parent Registration | REAL | `POST /api/v1/auth/register/` | `dataSources.auth: "api"` |
| `/terms` | Terms of Service | STATIC (Draft) | Static placeholder markup | `STATIC` |
| `/privacy` | Privacy Policy (DPDP Act) | STATIC (Draft) | Static placeholder markup | `STATIC` |
| `/forgot-password` | Account Recovery Notice | STATIC | Static notice to contact school admin | `STATIC` |
| `/admin` | Identity & School Header | REAL | `GET /api/v1/auth/me/` | `dataSources.auth: "api"` |
| `/admin` | 4 KPI Cards (Students/Teachers) | REAL | `GET /api/v1/dashboard/stats/` | `dataSources.dashboard: "api"` |
| `/admin/students` | Student Directory & Admissions | REAL | `GET, POST /api/v1/admin/students/`, `PATCH, DELETE /api/v1/admin/students/:id/` | `dataSources.students: "api"` |
| `/admin/teachers` | Faculty & Staff Directory | REAL | `GET, POST /api/v1/admin/teachers/`, `PATCH, DELETE /api/v1/admin/teachers/:id/` | `dataSources.teachers: "api"` |
| `/admin/classes` | Classroom Sections CRUD | REAL | `GET, POST /api/v1/admin/classes/`, `PATCH, DELETE /api/v1/admin/classes/:id/` | `dataSources.classes: "api"` |
| `/admin/import` | 3-Step Bulk Student Admission | REAL | `POST /api/v1/admin/import/preview/`, `POST /api/v1/admin/import/confirm/` | `dataSources.students: "api"` |
| `/admin/schools` | Network Institutes Management (Superuser) | REAL | `GET, POST /api/v1/admin/schools/`, `PATCH, DELETE /api/v1/admin/schools/:id/` | `dataSources.schools: "api"` |
| `/admin/principals` | Principals & Directors Appointment (Superuser) | REAL | `GET, POST /api/v1/admin/principals/`, `DELETE /api/v1/admin/principals/:id/` | `dataSources.auth: "api"` |
| `/teacher` | Dashboard Home | REAL (counts) / MOCK (schedule) | `GET /api/v1/teacher/my-students/` | `dataSources.teachers: "api"` |
| `/teacher/attendance` | Context Banner & School | REAL | `GET /api/v1/auth/me/` | `dataSources.auth: "api"` |
| `/teacher/attendance` | Student Roster List | REAL (when assigned) / MOCK | `GET /api/v1/teacher/my-students/` (fallback `MOCK_ATTENDANCE_ROSTER`) | `dataSources.attendance: "mock"` |
| `/student` | Student Scholar Profile | REAL (profile) / MOCK (results) | `GET /api/v1/student/me/` | `dataSources.student_me: "api"` |
| `/parent` | Child Switcher & Overview | MOCK | `MOCK_PARENT_CHILDREN` | `dataSources.parent: "mock"` |
| `/parent` | Daily Attendance Card | MOCK | `MOCK_PARENT_ATTENDANCE` | `dataSources.parent: "mock"` |
| `/parent` | Fee Due & Result Cards | MOCK | `MOCK_PARENT_FEE_DUE`, `MOCK_PARENT_RESULT` | `dataSources.parent: "mock"` |
| `/parent` | School Circulars / Notices | MOCK | `MOCK_PARENT_NOTICES` | `dataSources.parent: "mock"` |

---

## 3. Backend Files Added or Edited

| File | Status | Rationale / Change |
|---|---|---|
| `school-management-system/requirements.txt` | EDITED | Pinned `djangorestframework==3.18.1` matching installed environment |
| `school-management-system/config/settings.py` | EDITED | Added `'rest_framework'`, `'api'` to `INSTALLED_APPS`; DRF session auth & `DEFAULT_THROTTLE_RATES` |
| `school-management-system/config/urls.py` | EDITED | Added `path('api/v1/', include('api.urls'))` route |
| `school-management-system/api/urls.py` | ADDED/EDITED | Routes for auth, schools, academics, dashboard, teacher, student, and admin CRUD/import |
| `school-management-system/api/views.py` | ADDED/EDITED | Public directory endpoints, auth endpoints, parent registration, role redirection |
| `school-management-system/api/views_admin.py` | ADDED | Institute Admin scoped CRUD (classes, teachers, students), Excel preview & atomic confirm, superuser-only schools and principals |
| `school-management-system/api/pagination.py` | ADDED | `StandardResultsSetPagination` providing 20-per-page pagination with total pages & records count |
| `school-management-system/api/permissions.py` | ADDED/EDITED | Permissions: `IsPrincipalOrSuperuser`, `IsSuperuserOnly`, `IsTeacher`, `IsStudent` |
| `school-management-system/api/serializers.py` | ADDED/EDITED | Serializers for User, School, Teacher, Class, Student, and Principal |
| `school-management-system/api/tests.py` | ADDED/EDITED | 19 automated unit tests covering auth, tenant isolation, cross-tenant 404s, cascades, import flow, superuser management |

---

## 4. How to Transition Mock Features to Real Backend

All data toggles are located in `Frontend/indoreedu-web/src/lib/config/dataSources.ts`. To transition a feature from mock to real:

1. **Academic News / Circulars (`USE_MOCK_NEWS = false`)**:
   - Backend needs: Notice board model (e.g., `academics.Notice` with title, category, date, content, school FK).
   - Endpoint needed: `GET /api/v1/academics/notices/`.
   - Action: Implement endpoint, update `src/lib/api/` client, toggle flag in `dataSources.ts`.

2. **Attendance Marking (`USE_MOCK_ATTENDANCE = false`)**:
   - Backend has: `academics.DailyAttendance` and `academics.AttendanceRecord`.
   - Endpoint needed: `POST /api/v1/academics/attendance/` accepting `{ date, student_ids: [ { id, status } ] }`.
   - Action: Wire submission button in `src/app/teacher/attendance/page.tsx` to POST endpoint.

3. **Parent Portal Data (`USE_MOCK_PARENT = false`)**:
   - Backend needs: Parent-student relationship query endpoint.
   - Endpoint needed: `GET /api/v1/parent/children/` and `GET /api/v1/parent/attendance/<student_id>/`.
   - Action: Replace `MOCK_PARENT_*` in `src/app/parent/page.tsx` with API client calls.

4. **Fee Accounting & Payments**:
   - Backend needs: Fee invoice / challan model (or integration with fees app).
   - Endpoint needed: `GET /api/v1/fees/invoices/` and `POST /api/v1/fees/pay/`.

5. **Visual Sample Tags Toggle**:
   - In production, set `NEXT_PUBLIC_SHOW_SAMPLE_TAGS=false` in `.env.local` to completely hide the amber "Sample" pills across all pages.

---

## 5. Known Limitations

1. **Student Dashboard Route**:
   - When a user logs in with role `student`, the API returns `redirectUrl: "/institutes"` because no dedicated student dashboard screen was exported in Stitch.
2. **Institute Lead Form**:
   - The "Enquire Now" form on `/institutes/[id]` simulates successful lead submission in client state. A CRM lead model is needed to persist enquiries.
3. **Session Cookies & HTTPS**:
   - In local development, cookies are transferred over HTTP (`SESSION_COOKIE_SECURE=False`). For production deployment, set `SESSION_COOKIE_SECURE=True` and `CSRF_COOKIE_SECURE=True` over HTTPS.
4. **Rate Limiting**:
   - Currently, Django login and public API endpoints do not have DRF throttling enabled. Recommend adding `AnonRateThrottle` before public launch.
