# Institute Admin Feature Set Test & Verification Checklist

This document provides end-to-end verification steps for the Institute Admin feature set implemented across the Django REST API (`api/`) and the Next.js frontend (`Frontend/indoreedu-web`).

---

## 1. Automated Quality Gates

Run these commands from PowerShell to verify code integrity and regression safety:

### Backend Checks
```powershell
cd "D:\pintu\My Projects\School Management System\school-management-system\school-management-system"

# 1. System check (must report 0 issues)
.\venv\Scripts\python.exe manage.py check

# 2. Migrations check (must report 'No changes detected')
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run

# 3. Automated API unit tests (19 tests covering auth, tenant isolation, CRUD, import, cascades)
.\venv\Scripts\python.exe manage.py test api
```

### Frontend Checks
```powershell
cd "D:\pintu\My Projects\School Management System\school-management-system\Frontend\indoreedu-web"

# 1. TypeScript verification (zero type errors)
npx tsc --noEmit

# 2. ESLint checks (zero errors/warnings)
npm run lint

# 3. Production build (all 21 static and dynamic pages compile successfully)
npm run build
```

---

## 2. Multi-Tenancy Scoping & Security Matrix

| Scenario | Actor | Target Resource | Expected HTTP Code | Expected Behavior |
|---|---|---|---|---|
| Read classes of School A | Principal A | `/api/v1/admin/classes/` | `200 OK` | Returns only School A classes |
| Read class belonging to School B | Principal A | `/api/v1/admin/classes/<id_b>/` | `404 Not Found` | Strict 404 (prevents ID existence probing) |
| Read classes across all schools | Superuser | `/api/v1/admin/classes/` | `200 OK` | Returns network-wide classes |
| Access institutes list | Principal A | `/api/v1/admin/schools/` | `403 Forbidden` | Restricted to superusers only |
| Access principals list | Principal A | `/api/v1/admin/principals/` | `403 Forbidden` | Restricted to superusers only |
| Create class with forged school ID | Principal A | `POST /api/v1/admin/classes/` | `201 Created` | Server forces school to Principal A's school |
| Create teacher with weak password | Principal A | `POST /api/v1/admin/teachers/` | `400 Bad Request` | Returns password strength validation error |
| Confirm expired/tampered import token | Principal A | `POST /api/v1/admin/import/confirm/` | `400 Bad Request` | Returns invalid/expired token error |

---

## 3. Manual Functional Verification Steps

### Test 1: Classroom Sections (`/admin/classes`)
1. Log in at `http://localhost:3000/login` with principal credentials.
2. Navigate to `http://localhost:3000/admin/classes`.
3. Click **"Add Class"**:
   - Enter Grade: `10`, Section: `C`.
   - Select Class Teacher from dropdown (or leave unassigned).
   - Click "Create Class".
   - Verify class appears in the table with code `CLS-<id>`.
4. Click **Edit** icon:
   - Change section to `D`.
   - Click "Save Changes" -> verify table updates.
5. Click **Delete** icon:
   - Confirm in the destructive warning modal -> verify class is deleted.

### Test 2: Faculty Management (`/admin/teachers`)
1. Navigate to `http://localhost:3000/admin/teachers`.
2. Click **"Add Faculty"**:
   - Enter First Name: `Suresh`, Last Name: `Patel`.
   - Username: `suresh_patel`, Employee ID: `EMP-2024-99`.
   - Designation: `PGT Mathematics`, Qualification: `M.Sc., B.Ed.`.
   - Temporary Password: `Faculty@123`.
   - Click "Create Faculty Account".
3. **Credentials Modal**:
   - Verify modal pops up with role `Teacher`, Username `suresh_patel`, Password `Faculty@123`.
   - Click "Copy Details" -> verify clipboard copies.
   - Click "Done" -> verify teacher is listed in directory.
4. **Delete Cascade**:
   - Click Delete on `suresh_patel` -> confirm.
   - Verify both the `Teacher` record and underlying `User` record are removed.

### Test 3: Student Enrolment (`/admin/students`)
1. Navigate to `http://localhost:3000/admin/students`.
2. Click **"New Admission"**:
   - First Name: `Ananya`, Last Name: `Joshi`.
   - Admission No: `ADM-2024-501`.
   - Class Section: Select `Class 10-A`.
   - Gender: `Female`, DOB: `2008-07-12`.
   - Click "Enrol Student".
3. **Credentials Modal**:
   - Verify modal displays username `ananya_joshi` and initial password.
4. Filter by Class:
   - Select `Class 10-A` in dropdown -> verify table filters correctly.
5. Search:
   - Type `Ananya` in search bar -> verify search reacts instantly.

### Test 4: 3-Step Bulk Student Import (`/admin/import`)
1. Navigate to `http://localhost:3000/admin/import`.
2. **Step 1 (Upload)**:
   - Click "Sample Template" -> downloads `student_roster_template.csv`.
   - Drag or choose the CSV file.
   - Click "Validate & Preview File".
3. **Step 2 (Preview)**:
   - Verify target school name and code match the logged-in principal.
   - Verify preview table displays parsed rows with "Valid" checkmarks.
   - Click "Confirm & Enrol Students".
4. **Step 3 (Summary)**:
   - Verify summary card displays total processed, count enrolled, and 0 duplicates.
   - Click "View Student Directory" -> verify new students appear in `/admin/students`.

### Test 5: Superuser Administration (`/admin/schools` & `/admin/principals`)
1. Log in with superuser credentials (`is_superuser=True`).
2. Verify sidebar contains **"Institutes"** and **"Principals"** links.
3. Navigate to `/admin/schools`:
   - Click "New Institute" -> add school name `Devi Ahilya Institute`, code `DAI-09`, city `Indore`.
   - Verify school is listed across the network.
4. Navigate to `/admin/principals`:
   - Click "Appoint Principal" -> select `Devi Ahilya Institute`, create username `principal_dai`.
   - Verify credentials modal appears with assigned campus.
   - Log in as `principal_dai` -> verify scope is strictly locked to `Devi Ahilya Institute`.
