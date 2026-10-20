from datetime import timedelta
from django.core import mail
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from academic_year.models import AcademicYear
from academics.models import SchoolClass, Student, Teacher
from accounts.models import User
from schools.models import School

from .models import EmailVerificationToken, Organization, OrganizationMember, SchoolOrganization
from .services import create_organization_with_campus, switch_active_campus


class OrganizationsTests(APITestCase):
    def setUp(self):
        # Create an existing school and user for conflict & isolation tests
        self.other_user = User.objects.create_user(
            username="other_admin",
            email="other@campus.com",
            password="SecurePassword@123!",
            role="admin",
        )
        self.other_school = School.objects.create(
            name="Other School",
            code="OTH-09",
            address="Indore",
            city="Indore",
            principal=self.other_user,
        )

    def test_register_org_creates_org_school_principal_and_pending_status(self):
        res = self.client.post(
            "/api/v1/auth/register-org/",
            {
                "organizationName": "Prestige Group of Institutes",
                "campusName": "Prestige Main Campus",
                "username": "prestige_admin",
                "email": "admin@prestige.edu",
                "mobile": "9826012345",
                "password": "SecurePassword@123!",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "pending")
        self.assertIn("organization", res.data)
        self.assertIn("school", res.data)

        # Verify DB records
        org = Organization.objects.get(name="Prestige Group of Institutes")
        self.assertEqual(org.owner.username, "prestige_admin")

        school = School.objects.get(name="Prestige Main Campus")
        so = SchoolOrganization.objects.get(school=school)
        self.assertEqual(so.status, "pending")
        self.assertTrue(so.is_main_campus)
        self.assertEqual(so.organization, org)

        member = OrganizationMember.objects.get(organization=org, user=org.owner)
        self.assertEqual(member.role, "owner")

        # Verify email token created & email sent
        token_obj = EmailVerificationToken.objects.filter(user=org.owner).first()
        self.assertIsNotNone(token_obj)
        self.assertFalse(token_obj.is_used)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Verify your institution", mail.outbox[0].subject)

    def test_register_org_duplicate_username_or_email_returns_generic_error(self):
        # Username collision
        res_dup_u = self.client.post(
            "/api/v1/auth/register-org/",
            {
                "organizationName": "Duplicate Org",
                "username": "other_admin",
                "email": "unique@campus.com",
                "password": "SecurePassword@123!",
            },
        )
        self.assertEqual(res_dup_u.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res_dup_u.data)
        self.assertEqual(
            res_dup_u.data["detail"],
            "An account with these details could not be registered. Please check your information or sign in.",
        )

        # Email collision
        res_dup_e = self.client.post(
            "/api/v1/auth/register-org/",
            {
                "organizationName": "Duplicate Org 2",
                "username": "unique_admin_user",
                "email": "other@campus.com",
                "password": "SecurePassword@123!",
            },
        )
        self.assertEqual(res_dup_e.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res_dup_e.data)

    def test_register_org_throttling(self):
        # RegisterOrgThrottle is 5/hour; the 6th call from same IP should get 429
        for i in range(5):
            self.client.post(
                "/api/v1/auth/register-org/",
                {
                    "organizationName": f"Throttle Org {i}",
                    "username": f"throttle_user_{i}",
                    "email": f"throttle_{i}@org.com",
                    "password": "SecurePassword@123!",
                },
            )
        res_6th = self.client.post(
            "/api/v1/auth/register-org/",
            {
                "organizationName": "Throttle Org Exceeded",
                "username": "throttle_user_exceeded",
                "email": "exceeded@org.com",
                "password": "SecurePassword@123!",
            },
        )
        self.assertEqual(res_6th.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_unverified_school_cannot_access_dashboard_but_can_access_setup_wizard(self):
        user, org, school, raw_token = create_organization_with_campus({
            "organizationName": "Unverified Academy",
            "campusName": "Unverified Campus",
            "username": "unverified_dir",
            "email": "dir@unverified.edu",
            "mobile": "9826099999",
            "password": "SecurePassword@123!",
        })

        self.client.force_login(user)

        # Attempt to access dashboard stats -> 403 EMAIL_VERIFICATION_PENDING
        res_dash = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(res_dash.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_dash.data["code"], "EMAIL_VERIFICATION_PENDING")

        # But Setup Wizard IS accessible
        res_setup = self.client.get("/api/v1/setup/status/")
        self.assertEqual(res_setup.status_code, status.HTTP_200_OK)
        self.assertEqual(res_setup.data["status"], "pending")
        self.assertEqual(res_setup.data["overallProgress"], 0)

    def test_verify_email_activates_school_and_grants_dashboard_access(self):
        user, org, school, raw_token = create_organization_with_campus({
            "organizationName": "Verifiable Org",
            "campusName": "Verifiable Campus",
            "username": "verify_user",
            "email": "verify@indore.edu",
            "mobile": "9826077777",
            "password": "SecurePassword@123!",
        })

        # Call verify-email endpoint
        res = self.client.get(f"/api/v1/auth/verify-email/?token={raw_token}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "active")

        # SchoolOrganization is now active
        so = SchoolOrganization.objects.get(school=school)
        self.assertEqual(so.status, "active")

        # Token is single-use: second attempt fails
        res_replay = self.client.get(f"/api/v1/auth/verify-email/?token={raw_token}")
        self.assertEqual(res_replay.status_code, status.HTTP_400_BAD_REQUEST)

        # Now dashboard stats returns 200
        self.client.force_login(user)
        res_dash = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(res_dash.status_code, status.HTTP_200_OK)

    def test_multi_campus_switching_and_tenant_isolation(self):
        user, org, school_a, _ = create_organization_with_campus({
            "organizationName": "IPS Academy",
            "campusName": "IPS Main Campus",
            "username": "ips_admin",
            "email": "admin@ips.edu",
            "mobile": "9826055555",
            "password": "SecurePassword@123!",
        })

        # Activate organization
        SchoolOrganization.objects.filter(school=school_a).update(status="active")

        # Create a second campus in the same organization
        school_b = School.objects.create(
            name="IPS City Campus",
            code="IPS-CITY-09",
            address="South Tukoganj Indore",
            city="Indore",
        )
        SchoolOrganization.objects.create(
            school=school_b,
            organization=org,
            status="active",
            is_main_campus=False,
        )

        self.client.force_login(user)

        # List campuses
        res_list = self.client.get("/api/v1/organizations/campuses/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data), 2)
        campus_ids = [c["id"] for c in res_list.data]
        self.assertIn(school_a.id, campus_ids)
        self.assertIn(school_b.id, campus_ids)

        # Switch to school B
        res_switch = self.client.post(
            "/api/v1/organizations/switch-campus/",
            {"schoolId": school_b.id},
        )
        self.assertEqual(res_switch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_switch.data["schoolId"], school_b.id)

        # Scoped actions now target school B
        res_classes_b = self.client.post(
            "/api/v1/classes/",
            {"name": "Class 11", "section": "Science"},
        )
        self.assertEqual(res_classes_b.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SchoolClass.objects.filter(school=school_b).count(), 1)
        self.assertEqual(SchoolClass.objects.filter(school=school_a).count(), 0)

        # Tenant isolation: attempt to switch to an unowned school -> 403 Forbidden
        res_bad_switch = self.client.post(
            "/api/v1/organizations/switch-campus/",
            {"schoolId": self.other_school.id},
        )
        self.assertEqual(res_bad_switch.status_code, status.HTTP_403_FORBIDDEN)

        # Re-check membership validation: remove user from organization
        OrganizationMember.objects.filter(organization=org, user=user).delete()
        # Next request fails campus permission
        res_lost = self.client.post(
            "/api/v1/organizations/switch-campus/",
            {"schoolId": school_b.id},
        )
        self.assertEqual(res_lost.status_code, status.HTTP_403_FORBIDDEN)

    def test_setup_progress_endpoint_and_principal_classes(self):
        user, org, school, _ = create_organization_with_campus({
            "organizationName": "Progress Academy",
            "campusName": "Progress Campus",
            "username": "progress_admin",
            "email": "progress@campus.edu",
            "mobile": "9826044444",
            "password": "SecurePassword@123!",
        })
        SchoolOrganization.objects.filter(school=school).update(status="active")
        self.client.force_login(user)

        # Initial setup: 0 progress
        res_init = self.client.get("/api/v1/setup/status/")
        self.assertEqual(res_init.status_code, status.HTTP_200_OK)
        self.assertEqual(res_init.data["overallProgress"], 0)
        self.assertFalse(res_init.data["checklist"]["academicYear"]["completed"])
        self.assertFalse(res_init.data["checklist"]["classes"]["completed"])

        # Add Academic Year
        self.client.post(
            "/api/v1/academic-years/",
            {"name": "2026-2027", "startDate": "2026-04-01", "endDate": "2027-03-31", "isCurrent": True},
        )

        # Add Class via principal_classes API
        res_create_cls = self.client.post(
            "/api/v1/classes/",
            {"name": "10", "section": "A"},
        )
        self.assertEqual(res_create_cls.status_code, status.HTTP_201_CREATED)

        # Verify duplicate class in same school is rejected
        res_dup_cls = self.client.post(
            "/api/v1/classes/",
            {"name": "10", "section": "A"},
        )
        self.assertEqual(res_dup_cls.status_code, status.HTTP_400_BAD_REQUEST)

        # Check progress updated to 50% (Academic Year + Classes completed)
        res_prog = self.client.get("/api/v1/setup/status/")
        self.assertEqual(res_prog.status_code, status.HTTP_200_OK)
        self.assertEqual(res_prog.data["overallProgress"], 50)
        self.assertTrue(res_prog.data["checklist"]["academicYear"]["completed"])
        self.assertTrue(res_prog.data["checklist"]["classes"]["completed"])
        self.assertEqual(res_prog.data["checklist"]["classes"]["count"], 1)
