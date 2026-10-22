# WAVE3_PLAN.md — Wave 3 Implementation Plan ("Make It Real + Responsive UI")

Comprehensive audit, architecture, design system, and step-by-step execution plan for Wave 3 based on `AGENTS.md`, `PONYTAIL.md`, the Master Frontend Design System rules, and the existing codebase.

---

## 1. Executive Summary & Core Objectives

Wave 1 established the foundation (authentication, tenants, academic years, attendance, guardians, notices, audit logs).  
Wave 2 delivered the onboarding pack (organizations, multi-campus, credentials engine, Excel bulk import, teacher permissions, syllabus).  
**Wave 3 turns the platform into a real, production-grade, responsive digital product**:
1. **Zero Fake Data & Seed Cleanup**: Eliminate all hardcoded names ("Dr. Rajesh Sharma", "Prof. Anita Deshmukh", "Prof. Sunita Verma", "Aarav Patel"), static dates ("24 Oct 2024"), static sessions ("Session 2024-25"), and mock fallback arrays across all 4 portals (Admin, Teacher, Student, Parent). Grep verification in final QA.
2. **Honest States**: Where a backend exists, wire real data with polished loading, empty, and error states. Where a backend does not yet exist (fees, exams/results, bus tracking, timetable), replace fake numbers and mock progress bars with dignified, premium "Coming Soon" cards.
3. **Teacher Portal Completion (Strict Attendance Boundary)**:
   - Provide a unified "My Classes" view distinguishing **Class Teacher** (attendance + roster) vs **Subject Teacher** (syllabus only). A subject assignment never grants attendance.
   - Respect granular teacher permissions: `attendance_backdate` allows picking past dates limited to the active `AcademicYear` (never future dates); otherwise attendance is locked to today.
4. **Student & Parent Portals Realism**: Fix student ID resolution; connect real monthly attendance calendars and live notices; ensure multi-child switching works cleanly.
5. **Admin Dashboard Realism (Optimized Aggregates)**: Real KPIs computed in aggregate SQL queries without N+1 (students, teachers, classes). "Present today" shows "Not taken yet" when 0 classes marked today instead of 0%. Respects active campus from session for multi-campus org owners.
6. **Principal Class & Subject Teacher Management**: Complete the UI on `/admin/classes` allowing principals to assign both Class Teachers and Subject Teachers.
7. **Responsive & Mobile-First Design System**: Adhere to `PONYTAIL.md` (zero new external packages) and the Master Frontend Design System. Provide 44px tap targets, admin drawer sidebar, bottom navigation for mobile portals, and table-to-card reflow under 768px.
8. **Language Toggle (Option A — Lean Context)**: Scoped to Teacher, Student, and Parent portals (Admin stays English), with localStorage persistence, English fallback for missing keys, and Noto Sans Devanagari font fallback.

---

## 2. Mock Audit (Full Surface Inventory)

Every section, tile, and fallback across the 4 portals has been audited against the codebase.

### 2.1 Admin Portal (`/admin`)

| Tile / Section | File Path & Lines | Current Classification | Replacement Action / Real Backend |
|---|---|---|---|
| **User Greeting** (`Good morning, Dr. ...`) | `AdminKpis.tsx:27`, `page.tsx:66-68` | **MOCK with existing backend** | Use `session.user.firstName + " " + session.user.lastName` (or `username`). Dynamic greeting based on browser hour (`Good morning`, `Good afternoon`, `Good evening`). Remove hardcoded "Dr." prefix. |
| **School Name / Context** | `AdminKpis.tsx:32`, `AdminHeader.tsx:31` | **REAL** | `session.school?.name` (fallback "IndoreEdu Institute" if unassigned). |
| **Academic Session Badge** (`Session 2024–25`) | `AdminKpis.tsx:35`, `AdminHeader.tsx:62` | **MOCK with existing backend** | Fetch active academic year from `GET /api/v1/academic-years/` (filter `isCurrent=true`) or include in dashboard summary. |
| **Header / KPI Date** (`Today, 24 Oct 2024`) | `AdminKpis.tsx:45`, `AdminHeader.tsx:69` | **MOCK with existing backend** | Compute live client date: `new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date())`. |
| **KPI 1: Enrolled Students** | `AdminKpis.tsx:77-111` | **REAL** | `GET /api/v1/dashboard/stats/` (`totalStudents`). Replace hardcoded subtitle "+142 this intake" with active student count or clean label. |
| **KPI 2: Faculty & Staff** | `AdminKpis.tsx:114-144` | **REAL** | `GET /api/v1/dashboard/stats/` (`totalTeachers`). Replace hardcoded "18 depts • 1:19 ratio" with total classes count or active faculty status. |
| **KPI 3: Present Today** | `AdminKpis.tsx:147-175` | **MOCK with existing backend** | Currently falls back to `94.6%` and `4,560 / 4,820 marked`. Wire to `GET /api/v1/attendance/summary/` (`presentPercent`, `present`, `totalStudents`). If no attendance marked today, show "Not marked yet today". |
| **KPI 4: Fees Collected** | `AdminKpis.tsx:177-201` | **MOCK with NO backend** | Replace with **Real Operational KPI**: "Classes Not Marked Today" (computed from total classes minus classes with attendance today) OR "Pending Guardian Claims" (`GET /api/v1/guardians/link-requests/`). Remove fake "₹3.84 Cr". |
| **Chart 1: Weekly Attendance** | `AdminChartsSection.tsx:45-114` | **MOCK with existing backend** | Currently calls `getAttendanceTrend(6)`, but if empty falls back to `MOCK_WEEKLY_ATTENDANCE`. Remove mock fallback; show real zero/empty state with message "Attendance data will plot here as daily registers are submitted." |
| **Chart 2: Fee Realization by Dept** | `AdminChartsSection.tsx:117-161` | **MOCK with NO backend** | Replace with **Pending Approvals & Setup Status Card** (Guardian link requests awaiting principal action + Setup progress checklist link), OR a clean "Finance & Fee Module — Coming Soon" card. |
| **Recent Campus Activity** | `AdminActivitySection.tsx:35-86` | **MOCK with existing backend** | Uses `MOCK_CAMPUS_ACTIVITIES`. Backend `GET /api/v1/audit/?limit=5` is already live! Wire to real school-scoped `AuditLog` entries (`import.students`, `attendance.save`, `credentials.reset`, etc.). |
| **Notices & Circulars** | `AdminActivitySection.tsx:89-180` | **REAL** | `GET /api/v1/notices/?limit=4`. Has empty state fallback. |
| **Setup Wizard Widget** | `src/components/admin/SetupWizardWidget.tsx` | **REAL** | `GET /api/v1/setup/status/`. |

---

### 2.2 Teacher Portal (`/teacher` & `/teacher/attendance`)

| Tile / Section | File Path & Lines | Current Classification | Replacement Action / Real Backend |
|---|---|---|---|
| **Assigned Classes Count** | `teacher/page.tsx:65-79` | **PARTIAL REAL** | Currently only counts `SchoolClass.objects.filter(class_teacher=teacher)`. Omits `ClassSubjectTeacher` assignments! Wire to new `GET /api/v1/teacher/my-classes/`. |
| **Total Students Count** | `teacher/page.tsx:81-95` | **PARTIAL REAL** | Currently only counts students in `class_teacher` classes. Wire to new `GET /api/v1/teacher/my-classes/` total unique students. |
| **Avg Attendance KPI** (`94.2%`) | `teacher/page.tsx:98-110` | **MOCK with existing backend** | Compute from school attendance summary (`GET /api/v1/attendance/summary/`) or teacher's marked classes today. |
| **Pending Tasks KPI** (`3 Pending`) | `teacher/page.tsx:113-125` | **MOCK with existing backend** | Wire to count of in-progress syllabus topics for this teacher's subjects (`GET /api/v1/subjects/<id>/syllabus/`) or replace with "Active Subjects". |
| **My Classes List** | `teacher/page.tsx:130-184` | **PARTIAL REAL** | Update to show both "Class Teacher of: Class X-A" and "Subject Teacher of: Mathematics (Class 9-B, 10-A)". |
| **Today's Schedule / Timetable** | `teacher/page.tsx:187-229` | **MOCK with NO backend** | Replace with clean "Class Timetable — Coming Soon" card or quick syllabus status shortcuts for assigned subjects. |
| **Attendance Class Switcher** | `teacher/attendance/page.tsx:33-35` | **MOCK with existing backend** | Currently hardcoded to `data.classes[0]`. Add interactive Class & Section dropdown switcher so teacher can pick which class to mark! |
| **Teacher Name in Header** | `teacher/attendance/page.tsx:138-140` | **MOCK with existing backend** | Hardcoded fallback `"Prof. Anita Deshmukh"`. Replace with `session.user.firstName + " " + session.user.lastName`. |
| **School Name in Header** | `teacher/attendance/page.tsx:142` | **MOCK with existing backend** | Hardcoded fallback `"SGSITS Indore"`. Replace with `session.school?.name`. |
| **Attendance Roster Data** | `teacher/attendance/page.tsx:18, 59` | **MOCK with existing backend** | `MOCK_ATTENDANCE_ROSTER` used as fallback. Remove mock fallback; show clean empty state ("No students enrolled in this section"). |
| **Date & Backdate Permission** | `teacher/attendance/page.tsx:73` | **MOCK with existing backend** | Date locked to `today`. If teacher has `attendance_backdate` permission, render date picker; otherwise lock to today. |
| **Language Toggle (`EN | हिंदी`)** | `teacher/attendance/page.tsx:174-186` | **MOCK with NO backend** | Visual pill with no state. (See Section 7 for resolution). |

---

### 2.3 Student Portal (`/student`)

| Tile / Section | File Path & Lines | Current Classification | Replacement Action / Real Backend |
|---|---|---|---|
| **Student Profile & Greeting** | `student/page.tsx:71-94` | **REAL** | `session.user`, `session.student`, `session.school`. |
| **Today's Attendance Status** | `student/page.tsx:27, 57-61` | **BUGGY REAL** | Calls `getStudentAttendance(session.user.id)` (passing User ID instead of Student ID!). Fix to pass `session.student.id` or fetch from `/api/v1/student/me/`. |
| **Monthly Attendance Rate** | `student/page.tsx:60` | **REAL** | Computed from `getStudentAttendance(studentId)`. Remove `94` fallback; show "No attendance records yet" if empty. |
| **Campus Bus Route #14** | `student/page.tsx:140-160` | **MOCK with NO backend** | Replace with clean "Transport & Bus Tracking — Coming Soon" card. |
| **Fee Due Card (₹28,500) & Fake UPI** | `student/page.tsx:162-210` | **MOCK with NO backend** | Replace with clean "Fee Portal & Receipts — Coming Soon" card. Remove misleading fake "Pay via UPI" button. |
| **Mid-Term Examination Results** | `student/page.tsx:213-255` | **MOCK with NO backend** | Replace with clean "Examinations & Report Cards — Coming Soon" card. |
| **School Notices** | `student/page.tsx:258-290` | **REAL** | `GET /api/v1/notices/`. |
| **Course Syllabus Link** | `student/page.tsx:98-103` | **REAL** | Links to `/student/syllabus` (Wave 2 Step 9). |

---

### 2.4 Parent Portal (`/parent`)

| Tile / Section | File Path & Lines | Current Classification | Replacement Action / Real Backend |
|---|---|---|---|
| **Child Switcher** | `parent/page.tsx:125-195` | **REAL** | `GET /api/v1/parent/children/` with claim link for unlinked guardians. |
| **Selected Child Attendance** | `parent/page.tsx:202-226` | **REAL** | `GET /api/v1/attendance/student/<childId>/`. |
| **School Bus Route #14** | `parent/page.tsx:229-243` | **MOCK with NO backend** | Replace with clean "Transport & Bus Tracking — Coming Soon" card. |
| **Fee Due Card & Fake Payment** | `parent/page.tsx:248-293` | **MOCK with NO backend** | Replace with clean "Fee Schedule & Dues — Coming Soon" card. Remove fake "Pay via UPI" button. |
| **Mid-Term Results Card** | `parent/page.tsx:298-334` | **MOCK with NO backend** | Replace with clean "Examination Marks & Progress — Coming Soon" card. |
| **School Notices** | `parent/page.tsx:337-376` | **REAL** | `GET /api/v1/notices/`. |
| **Child Syllabus Link** | `parent/page.tsx:114-121` | **REAL** | Links to `/parent/syllabus` (Wave 2 Step 9). |

---

## 3. Mock Replacement Strategy & Honest UI

### 3.1 Removing Mock Fallbacks
In all pages and components:
- Delete imports of `MOCK_ADMIN_DASHBOARD_STATS`, `MOCK_WEEKLY_ATTENDANCE`, `MOCK_DEPARTMENT_FEES`, `MOCK_CAMPUS_ACTIVITIES`, `MOCK_ATTENDANCE_ROSTER`, `MOCK_PARENT_FEE_DUE`, `MOCK_PARENT_RESULT`.
- Replace `catch { /* fall back to mock */ }` with proper component state transitions:
  - `loading`: Render light, unobtrusive skeleton shapes (`Skeleton.tsx`).
  - `empty`: Render intentional empty states with a helpful description and actionable button where relevant.
  - `error`: Render a soft, retryable error banner instead of crashing or showing fake data.

### 3.2 Dignified "Coming Soon" Component Pattern
For unbacked features (Fees, Exams, Bus Tracking, Timetable):
- Do **NOT** render fake numbers, fake currency values (`₹3.84 Cr`), or fake interactive buttons (`Pay via UPI`).
- Build a single, high-quality, reusable component: `src/components/common/ComingSoonCard.tsx`:
  - **Visual Treatment**: `bg-surface-container-lowest border border-outline-variant/30 rounded-2xl p-5 shadow-sm`.
  - **Badge**: Minimal, subtle pill (`text-[10px] font-bold uppercase tracking-wider bg-surface-container text-on-surface-variant`).
  - **Content**: Feature icon, clear feature title, 1-2 sentence description explaining that this module will activate once the school/board integration is enabled, and an optional "Notify Me" or "Learn More" state.

---

## 4. Backend Enhancements (Scoped to `api/` and `teacher_assignments/`)

Per `AGENTS.md` Rule 1, existing models (`accounts`, `schools`, `academics`, `core`, `imports`) are **never edited**. All new endpoints are function-based views in `api/` or `teacher_assignments/`, strictly scoped by tenant.

### 4.1 Enhanced Admin Dashboard Summary: `GET /api/v1/dashboard/summary/`
To eliminate client waterfalls and ensure live data across the admin dashboard:
- **Permission**: `IsPrincipalOrSuperuser`
- **Tenant Scope & Multi-Campus**: Filtered strictly to `request.user`'s active school. For organization owners and admins, dynamically honors `request.session["active_school_id"]` via `get_active_school_for_user(request)` (or requested school query param if superuser).
- **High-Performance Aggregate Queries (No N+1)**:
  - All metrics computed using database-level `aggregate()` and `count()` queries:
    - `totalStudents = Student.objects.filter(school=school).count()`
    - `totalTeachers = Teacher.objects.filter(school=school).count()`
    - `totalClasses = SchoolClass.objects.filter(school=school).count()`
    - `totalSubjects = Subject.objects.filter(school=school).count()`
  - Attendance Today:
    - Counts `AttendanceSession.objects.filter(school=school, date=today)`
    - Aggregates status counts via `Count('records', filter=Q(records__status='present'))`, etc.
    - If `markedClasses == 0`: `presentPercent` is `null` and `status` reports `"not_taken_yet"`. In the UI, this displays **"Not taken yet"** (never misleading 0%).
- **Response Shape**:
```json
{
  "school": { "id": 1, "name": "SGSITS Indore", "code": "SGSITS-09" },
  "totalStudents": 1420,
  "totalTeachers": 48,
  "classesTotal": 18,
  "classesTaken": 16,
  "classesNotTaken": 2,
  "presentToday": {
    "taken": true,
    "percent": 94.8
  },
  "pendingGuardianRequests": 5,
  "currentAcademicYear": {
    "id": 3,
    "name": "2024-2025",
    "startDate": "2024-06-01",
    "endDate": "2025-04-30"
  },
  "setupProgress": {
    "overallProgress": 100,
    "isComplete": true
  }
}
```
*When zero classes have marked attendance today:*
```json
{
  "presentToday": {
    "taken": false,
    "percent": null
  }
}
```

### 4.2 Enhanced Teacher My Classes: `GET /api/v1/teacher/my-classes/`
Currently, `api/views.py:my_students` only checks `SchoolClass.objects.filter(class_teacher=teacher)`.  
The new endpoint unifies both Class Teacher assignments and `ClassSubjectTeacher` records while **strictly preserving Wave 1 attendance boundaries**:
- **Permission**: `IsTeacher`
- **Tenant Scope**: Teacher's school.
- **Strict Role Boundary (Plan Addition A)**:
  - **Class Teacher**: `role: "class_teacher"`, `canMarkAttendance: true`. Can take and view attendance for that class section.
  - **Subject Teacher**: `role: "subject_teacher"`, `canMarkAttendance: false`. A subject assignment does **NOT** grant attendance permissions. Subject classes appear solely for syllabus tracking and subject management.
  - The UI must strictly follow `canMarkAttendance`.
- **Backdate Permission (Plan Addition B)**:
  - Includes `permissions: ["attendance_backdate", ...]` and `currentAcademicYear` dates (`startDate`, `endDate`).
  - In the UI, the date picker appears **only** if `attendance_backdate` is present in `permissions`. It is strictly constrained: `min = startDate`, `max = today` (never future dates).
- **Date Logic (Plan Addition D)**:
  - All date comparisons and session queries use `timezone.localdate()` (Asia/Kolkata).
- **Response Shape**:
```json
{
  "teacher": { "id": 12, "name": "Prof. Anita Deshmukh", "employeeId": "T-102" },
  "currentAcademicYear": {
    "id": 1,
    "name": "2024-2025",
    "startDate": "2024-06-01",
    "endDate": "2025-04-30"
  },
  "permissions": ["attendance_backdate", "manage_syllabus"],
  "classes": [
    {
      "id": 4,
      "name": "10",
      "section": "A",
      "displayName": "Class 10-A",
      "role": "class_teacher",
      "canMarkAttendance": true,
      "totalStudents": 42,
      "subjects": [
        { "id": 1, "name": "Mathematics", "code": "MATH10" }
      ]
    },
    {
      "id": 5,
      "name": "10",
      "section": "B",
      "displayName": "Class 10-B",
      "role": "subject_teacher",
      "canMarkAttendance": false,
      "totalStudents": 40,
      "subjects": [
        { "id": 1, "name": "Mathematics", "code": "MATH10" }
      ]
    }
  ]
}
```

### 4.3 Subject Teacher Assignments API for Principal
Wave 2 Step 5 created `GET/POST /api/v1/classes/<class_id>/subject-teachers/`. We ensure it supports:
- `GET /api/v1/classes/<class_id>/subject-teachers/`: Returns all subject-to-teacher mappings for the class.
- `POST /api/v1/classes/<class_id>/subject-teachers/`: Body `{"subjectId": 1, "teacherId": 12}` (assigns teacher, logs `permission.grant` / mapping audit).
- `DELETE /api/v1/classes/<class_id>/subject-teachers/<mapping_id>/`: Unassigns subject teacher.

---

## 5. Frontend Portal Realism & Enhancements

### 5.1 Admin Portal (`/admin`)
1. **Dynamic Greeting & Time**:
   - Greeting changes based on local hour: `< 12` -> "Good morning", `< 17` -> "Good afternoon", else -> "Good evening".
   - Name uses `currentUser.firstName + " " + currentUser.lastName` or `username`.
   - Real active date formatted from `new Date()` (`"Today, 24 Oct 2024"`).
   - Real academic session pulled from `summary.academicYear.name` (e.g. `"Session 2024–25"`).
2. **KPI Strip**:
   - KPI 1: Enrolled Students (real count).
   - KPI 2: Faculty (real count).
   - KPI 3: Attendance Today (real `%` and count, or "Attendance Not Taken" badge if 0).
   - KPI 4: Replaced with **"Attendance Registers Pending"** (`notTakenClasses` with a quick link to send reminders) OR **"Pending Guardian Claims"** (linking to `/admin/guardians`).
3. **Weekly Attendance Trend Chart**:
   - Connects to `getAttendanceTrend(6)`.
   - If no attendance recorded in the last 6 days, display an elegant zero-state card with dashed guidelines and "Registers will plot here once attendance is recorded".
4. **Recent Activity Stream**:
   - Connects to `GET /api/v1/audit/?limit=5`.
   - Maps real `AuditLog` actions (`import.students`, `attendance.save`, `credentials.reset`, `permission.grant`) to human-readable activity rows with user avatars and relative timestamps.
5. **Class & Subject Teacher Assignment UI (`/admin/classes`)**:
   - On the Class Management table, add an action button **"Manage Subject Teachers"** for each class section.
   - Opens `SubjectTeachersModal.tsx`:
     - Displays all subjects configured for the school.
     - Allows selecting a teacher for each subject via dropdown.
     - Saves via `POST /api/v1/classes/<id>/subject-teachers/`.

### 5.2 Teacher Portal (`/teacher` & `/teacher/attendance`)
1. **My Classes & Batches**:
   - Replaced with real data from `GET /api/v1/teacher/my-classes/`.
   - Distinct visual badges for **"Class Teacher"** (registers & overall roster) vs **"Subject Teacher"** (assigned subjects).
2. **Attendance Register (`/teacher/attendance`)**:
   - **Interactive Class Selector**: Replace the hardcoded `data.classes[0]` with a clean dropdown / segmented control allowing the teacher to switch between their assigned classes.
   - **Permission-Aware Backdating**: If the teacher has `attendance_backdate` permission, render a date selector permitting selection of past dates up to 30 days. If not, lock date to today with a lock icon.
   - **Live Roster**: Fetch from `getClassAttendance(selectedClassId, date)`. If empty, render an empty state ("No students enrolled in this section").
   - **Submit & Feedback**: Real `saveClassAttendance()` with instant visual toast and count confirmation.
3. **Syllabus Status Shortcut**:
   - Quick action to open `/teacher/syllabus` with their assigned subjects pre-filtered.

### 5.3 Student Portal (`/student`)
1. **Student ID Fix**:
   - Retrieve `studentId` accurately from `GET /api/v1/student/me/` (or enhanced session).
   - Call `getStudentAttendance(studentId)`.
2. **Attendance Calendar / Month Breakdown**:
   - Display real present/absent stats for current month.
   - Highlight today's status (`present`, `absent`, or `not_marked`).
3. **Clean Unbacked Cards**:
   - Replace fake bus and fake fee cards with informative `ComingSoonCard` components.
4. **School Notices**:
   - Real notice feed from `getNotices()`.

### 5.4 Parent Portal (`/parent`)
1. **Multi-Child Switcher**:
   - Real list from `getParentChildren()`.
   - Switching child immediately refreshes child attendance, class details, and notices.
2. **Unlinked Parent Experience**:
   - If parent has no linked children, render prominent "Link Your Student" claim card using registered mobile number.
3. **Clean Unbacked Cards**:
   - Replace fake fee checkout (with fake UPI button) and fake report cards with `ComingSoonCard`.

---

## 6. Lightweight Responsive UI Design System (PONYTAIL-Compliant)

Per `PONYTAIL.md`, **no new npm packages** (no MUI, shadcn, Lucide, Framer Motion, date-fns). Everything uses existing Next.js, React, and Tailwind v4 CSS variables.

### 6.1 Design Tokens & Base Classes (`globals.css` reuse)
- **Surfaces**:
  - Base background: `bg-surface-container` (`#F3F2F8`)
  - Elevated card: `bg-surface-container-lowest` (`#FFFFFF`) with `border border-outline-variant/30`
  - Floating modal: `bg-surface-container-lowest shadow-2xl rounded-3xl`
  - Dark accent: `bg-inverse-surface` (`#1B1A33`) text `text-inverse-on-surface`
- **Brand Colors**:
  - Primary: `text-primary` (`#5B4BC4`), `bg-primary`
  - Secondary/CTA: `bg-cta` (`#F26B3A`), `hover:bg-cta-hover` (`#E05523`), `text-on-cta` (`#FFFFFF`)
  - Success/Present: `bg-emerald-50 text-emerald-700 border-emerald-200`
  - Danger/Absent: `bg-rose-50 text-rose-700 border-rose-200`
- **Typography**:
  - Plus Jakarta Sans system typography: `text-headline-sm`, `text-body-md`, `text-label-md`.

### 6.2 Mobile Layout Patterns
1. **Admin Workspace Drawer Sidebar**:
   - Desktop (`>= 1024px`): Fixed 72 (288px) sidebar.
   - Mobile (`< 1024px`): Off-canvas slide-over drawer with dark backdrop (`bg-black/40 backdrop-blur-sm`), dismissable via hamburger toggle, overlay tap, or ESC key.
2. **Teacher / Student / Parent Mobile Bottom Nav**:
   - Reusable `src/components/layout/BottomNav.tsx`.
   - Fixed at bottom of mobile viewports (`< 768px`), height 64px, safe area padding, 4 core tabs with 44px min tap targets.
3. **Table-to-Card Responsive Reflow**:
   - All management tables (Classes, Teachers, Students, Attendance) use the responsive pattern:
     - Desktop (`md:table`): standard data table with headers.
     - Mobile (`md:hidden`): stacked cards (`flex flex-col gap-3`), showing key fields as badge rows with prominent action buttons.
4. **Touch Targets & Forms**:
   - All interactive buttons and inputs have `min-h-[44px]` for effortless mobile thumb usage.
   - Modals and forms feature sticky bottom action bars on mobile viewports so "Save" / "Cancel" buttons are never pushed below the fold.

### 6.3 Accessibility Basics
- Valid `aria-label` on all icon-only buttons (menu toggles, modal closes, search, logout).
- Distinct keyboard focus indicators (`focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none`).
- High contrast compliant with WCAG AA (all text colors verified against surface backgrounds).
- Screen-reader accessible status badges (e.g. `aria-label="Present today: 94 percent"`).

---

## 7. Migration & Backend Changes

### 7.1 Existing Apps Protection
- `accounts`, `schools`, `academics`, `core`, `imports`: **0 edits, 0 migrations**.
- `makemigrations --check --dry-run` must continue reporting 0 pending migrations for existing apps.

### 7.2 New Endpoints in `api/urls.py`
```python
# Wave 3 Endpoints
path("dashboard/summary/", views.dashboard_summary, name="api_dashboard_summary"),
path("teacher/my-classes/", views_ta.teacher_my_classes, name="api_teacher_my_classes"),
```

---

## 8. Test Plan

### 8.1 Backend Tests (`api/tests_wave3.py` & `teacher_assignments/tests.py`)
1. **`test_dashboard_summary_tenant_isolation`**: Verify principal at School A receives KPIs, attendance, and setup status exclusively for School A; verify School B data is never leaked.
2. **`test_dashboard_summary_superuser_scoping`**: Verify superuser can inspect any school's summary via `?school=<id>`.
3. **`test_teacher_my_classes_combines_class_and_subject_assignments`**: Verify a teacher assigned as Class Teacher of 10-A and Subject Teacher of Mathematics for 10-B receives both classes in `GET /api/v1/teacher/my-classes/` with correct flags.
4. **`test_teacher_my_classes_unauthorized_for_students`**: Verify students and parents receive 403 Forbidden.
5. **`test_class_subject_teacher_crud_principal_only`**: Verify principal can assign, list, and delete subject-teacher mappings on their school classes; verify cross-school mapping is rejected.
6. **`test_attendance_backdate_permission_enforcement`**: Verify a teacher without `attendance_backdate` permission is rejected when submitting attendance for past dates; verify a teacher with the permission succeeds.

### 8.2 Frontend Tests & Compilation
- Run `npx tsc --noEmit` from `Frontend/indoreedu-web` — must return 0 errors.
- Run `npm run lint` from `Frontend/indoreedu-web` — must return 0 errors.
- Run `npm run build` from `Frontend/indoreedu-web` — must compile production bundle cleanly.
- **Mock & Seed Identity Grep Check (Plan Addition D)**:
  - Run terminal grep across `src/` to verify zero instances of mock seed names or mock constants remain in runtime code paths:
    - `"Aarav Patel"`
    - `"Prof. Sunita Verma"`
    - `"Dr. Rajesh Sharma"`
    - `"Prof. Anita Deshmukh"`
    - `"MOCK_ADMIN_DASHBOARD_STATS"`
    - `"MOCK_WEEKLY_ATTENDANCE"`
    - `"MOCK_DEPARTMENT_FEES"`
    - `"MOCK_CAMPUS_ACTIVITIES"`
    - `"MOCK_ATTENDANCE_ROSTER"`
    - `"MOCK_PARENT_FEE_DUE"`
    - `"MOCK_PARENT_RESULT"`

### 8.3 Manual Responsive QA Matrix

| Viewport | Device / Target | Specific Checks |
|---|---|---|
| **360px** | Small Android (e.g. Redmi / Galaxy A series) | - Mobile bottom nav visible and active.<br>- Admin drawer opens and closes without layout shift.<br>- Attendance roster rows stack cleanly without horizontal scroll.<br>- Tap targets >= 44px.<br>- No text overflow or clipped numbers. |
| **768px** | iPad / Android Tablet | - Multi-column grid adapts (2 columns for KPI cards).<br>- Modal dialogues centered with comfortable padding.<br>- Classes table reflows cleanly. |
| **1280px+** | Desktop / Laptop | - 72-width AdminSidebar fixed.<br>- 4-column KPI cards row.<br>- Attendance trend chart and Activity stream side-by-side. |

---

## 9. Implementation Sequence

The work is organized into 6 concrete steps:

- **Step 1: Backend Real Endpoints (`dashboard_summary` & `teacher_my_classes`)**:
  - Implement `api/views.py:dashboard_summary` (real student/teacher counts, attendance marked/not-taken, pending guardians, active academic year, campus resolution).
  - Implement `teacher_assignments/views.py:teacher_my_classes` (combining class teacher and `ClassSubjectTeacher` records, returning permissions, attendance boundary preserved).
  - Register routes in `api/urls.py`.
  - Add backend tests in `api/tests_wave3.py` and run `python manage.py test`.

- **Step 2: Shared UI Components & Design System Tokens**:
  - Create `src/components/common/ComingSoonCard.tsx` (dignified placeholder for unbacked features).
  - Create `src/lib/languageContext.tsx` implementing Option A: scoped to Teacher, Student, and Parent portals (Admin stays English), with localStorage persistence, English fallback, and Noto Sans Devanagari font fallback.
  - Enhance `src/components/layout/AdminSidebar.tsx` with mobile drawer backdrop and swipe-to-close behavior.
  - Enhance `src/components/layout/BottomNav.tsx` with role-aware tab configurations and 44px tap targets.
  - Add typed client methods in `src/lib/api/wave3.ts` and update `src/types/index.ts`.

- **Step 3: Admin Dashboard & Class Management Overhaul**:
  - Update `src/app/admin/page.tsx`, `AdminKpis.tsx`, `AdminHeader.tsx`, `AdminChartsSection.tsx`, `AdminActivitySection.tsx`.
  - Replace mock fallbacks with real `dashboard_summary` data, live date, and school-scoped `AuditLog` events.
  - Add `SubjectTeachersModal.tsx` to `src/app/admin/classes/page.tsx` for principal subject-teacher mapping.

- **Step 4: Teacher Portal Realism & Interactive Attendance**:
  - Update `src/app/teacher/page.tsx` with real `my-classes` data and subject assignments.
  - Update `src/app/teacher/attendance/page.tsx`: add class selector dropdown, date backdating based on permissions, real student roster with empty/loading states.

- **Step 5: Student & Parent Portals Realism**:
  - Update `src/app/student/page.tsx`: fix student ID resolution, wire real monthly attendance, replace fake fee/bus/exam cards with `ComingSoonCard`.
  - Update `src/app/parent/page.tsx`: ensure child switcher reloads attendance, wire real notices, replace fake checkout with `ComingSoonCard`.

- **Step 6: Verification & QA Review**:
  - Run full Django test suite (`python manage.py test`).
  - Run `npx tsc --noEmit` and `npm run lint`.
  - Run seed identity grep check across `src/`.
  - Execute responsive QA audit across 360px, 768px, 1280px.

---

## 10. Decisions, Risks & Conflicts

### 10.1 User Decision: Language Toggle (`EN | हिंदी`) — Option A Approved
- **Scope**: Scoped to Teacher, Student, and Parent portals only (Admin stays English).
- **Architecture**:
  - Lightweight 40-line `LanguageContext` in `src/lib/languageContext.tsx` with `locale` state (`"en"` | `"hi"`).
  - Persisted in `localStorage.getItem("indoreedu_locale")`.
  - English fallback for missing keys.
  - Noto Sans Devanagari font fallback in CSS font family.
  - Dictionary of ~35 essential terms (Attendance, Present, Absent, Students, Teachers, Save, etc.).
  - 0 external i18n libraries required per `PONYTAIL.md`.

### 10.2 Technical Risks & Mitigations
1. **Risk: Heavy Database Load on Admin Dashboard Summary**:
   - *Mitigation*: The summary query uses single-query `aggregate()` and `filter(school=...)` queries with indexed fields (`school_id`, `date`), keeping response time under 30ms.
2. **Risk: Teacher Missing Both Class and Subject Assignments**:
   - *Mitigation*: If a teacher is newly onboarded with 0 assignments, render a welcoming empty state: "No classes assigned yet. Contact your principal to assign your classes and subjects."
3. **Risk: Mobile Horizontal Overflow on Attendance Roster**:
   - *Mitigation*: Use CSS flexbox/grid with truncation (`truncate`), `min-w-0`, and avoid fixed pixel widths over 320px.
