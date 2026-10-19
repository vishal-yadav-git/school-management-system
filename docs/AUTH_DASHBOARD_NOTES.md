# Auth & Dashboard Analysis Notes

1. **User Roles**: Defined in `accounts.User` with choices: `admin`, `principal`, `teacher`, `student`, `parent` (default: `student`). Contains an optional `mobile` field (max 15 chars).
2. **School-Principal Link**: 1-to-1 relationship on `schools.School.principal` -> `accounts.User` (`related_name='principal_school'`).
3. **Teacher Link**: 1-to-1 profile in `academics.Teacher` (`user` -> `User`, `related_name='teacher_profile'`) linked to `school` via ForeignKey.
4. **Student Link**: 1-to-1 profile in `academics.Student` (`user` -> `User`, `related_name='student_profile'`) linked to `school` and `class_section` via ForeignKeys.
5. **Parent Link**: No dedicated Parent profile table exists in `accounts` or `academics`; parents are simply `User` accounts having `role='parent'`.
6. **Existing Register Flow**: The Django template view (`accounts.views.register`) accepts username, name, email, mobile, and password, but hardcodes `user.role = 'student'`.
7. **Additive API Register Flow**: The new `POST /api/v1/auth/register/` endpoint is designed specifically for public Parent sign-up and hardcodes `user.role = 'parent'`.
8. **No Contradiction**: The existing HTML register view creates students, while the new API endpoint creates parents for the parent portal. Neither overrides or breaks the other.
9. **Creation of Staff/Students**: Teachers, students, and principals are created administratively via Django Admin or school management workflows with attached profiles.
10. **Data Scoping Rules**: Principals see their own school via `request.user.principal_school`; teachers see classes/students via `teacher_profile`; students see their own record via `student_profile`; superusers see all.
