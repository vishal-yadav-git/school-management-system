import os
import re
import pandas as pd

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from schools.models import School
from academics.models import Student, SchoolClass


User = get_user_model()


class Command(BaseCommand):
    help = "Import students from Excel or CSV file"

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path",
            type=str,
            help="Path of Excel or CSV file"
        )

    def normalize_column(self, column):
        """
        Convert Excel column names into simple names.
        Example:
        Student's Id -> student_id
        Student's Name -> student_name
        Mobile Number -> mobile_number
        """

        column = str(column).strip().lower()

        # Remove apostrophes
        column = column.replace("'", "")
        column = column.replace('"', "")

        # Replace special characters with spaces
        column = re.sub(r"[^a-z0-9]+", " ", column)

        # Remove extra spaces
        column = " ".join(column.split())

        # Convert spaces to underscore
        column = column.replace(" ", "_")

        return column

    def clean_value(self, value):
        if pd.isna(value):
            return ""

        return str(value).strip()

    def get_date(self, value):
        if pd.isna(value) or value == "":
            return None

        try:
            date_value = pd.to_datetime(
                value,
                errors="coerce"
            )

            if pd.isna(date_value):
                return None

            return date_value.date()

        except Exception:
            return None

    def get_fee(self, value):
        if pd.isna(value) or value == "":
            return 0

        try:
            value = str(value)

            value = value.replace("₹", "")
            value = value.replace(",", "")
            value = value.strip()

            return float(value)

        except Exception:
            return 0

    def handle(self, *args, **options):

        file_path = options["file_path"]

        # -----------------------------------------
        # FILE CHECK
        # -----------------------------------------

        if not os.path.exists(file_path):

            self.stdout.write(
                self.style.ERROR(
                    f"File not found: {file_path}"
                )
            )

            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Reading file: {file_path}"
            )
        )

        # -----------------------------------------
        # READ FILE
        # -----------------------------------------

        try:

            if file_path.lower().endswith(".csv"):

                df = pd.read_csv(file_path)

            else:

                excel_file = pd.ExcelFile(file_path)

                self.stdout.write(
                    f"Sheets found: {excel_file.sheet_names}"
                )

                # First sheet
                sheet_name = excel_file.sheet_names[0]

                df = pd.read_excel(
                    file_path,
                    sheet_name=sheet_name
                )

        except Exception as e:

            self.stdout.write(
                self.style.ERROR(
                    f"Error reading Excel: {e}"
                )
            )

            return

        # -----------------------------------------
        # NORMALIZE COLUMN NAMES
        # -----------------------------------------

        original_columns = list(df.columns)

        df.columns = [
            self.normalize_column(column)
            for column in df.columns
        ]

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Columns detected:"
            )
        )

        for original, normalized in zip(
            original_columns,
            df.columns
        ):

            self.stdout.write(
                f"  {original}  ->  {normalized}"
            )

        # -----------------------------------------
        # COLUMN ALIASES
        # -----------------------------------------

        aliases = {

            "student_id": [
                "student_id",
                "students_id",
                "student_s_id",
                "id"
            ],

            "student_name": [
                "student_name",
                "students_name",
                "student_s_name",
                "name"
            ],

            "father_name": [
                "father_name"
            ],

            "mother_name": [
                "mother_name"
            ],

            "address": [
                "address"
            ],

            "mobile_no": [
                "mobile_number",
                "mobile_no",
                "mobile"
            ],

            "alternate_mobile": [
                "alternate_mobile_number",
                "alternate_mobile_no",
                "alternate_mobile"
            ],

            "admission_date": [
                "admission_date"
            ],

            "fees": [
                "fee",
                "fees"
            ],

            "gender": [
                "gender"
            ],

            "class": [
                "class"
            ],

            "section": [
                "section"
            ],

            "date_of_birth": [
                "date_of_birth",
                "dob"
            ],

            "email": [
                "email"
            ],

            "caste": [
                "category",
                "caste"
            ],

            "transport": [
                "transport"
            ],

            "hostel": [
                "hostel"
            ],

            "school": [
                "school"
            ],

            "subject": [
                "subject"
            ],
        }

        # -----------------------------------------
        # FIND REAL COLUMN
        # -----------------------------------------

        column_map = {}

        for field, possible_names in aliases.items():

            for name in possible_names:

                if name in df.columns:

                    column_map[field] = name
                    break

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Column mapping:"
            )
        )

        for field, column in column_map.items():

            self.stdout.write(
                f"  {field} -> {column}"
            )

        # -----------------------------------------
        # REQUIRED FIELDS
        # -----------------------------------------

        required_fields = [
            "student_id",
            "student_name",
            "school"
        ]

        missing_fields = [
            field
            for field in required_fields
            if field not in column_map
        ]

        if missing_fields:

            self.stdout.write(
                self.style.ERROR(
                    f"Required columns missing: {missing_fields}"
                )
            )

            return

        # -----------------------------------------
        # TOTAL ROWS
        # -----------------------------------------

        total_rows = len(df)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Total Excel records: {total_rows}"
            )
        )

        # -----------------------------------------
        # COUNTERS
        # -----------------------------------------

        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        class_created_count = 0

        # -----------------------------------------
        # PROCESS EACH STUDENT
        # -----------------------------------------

        for index, row in df.iterrows():

            excel_row = index + 2

            try:

                # ---------------------------------
                # BASIC DATA
                # ---------------------------------

                student_id = self.clean_value(
                    row[column_map["student_id"]]
                )

                student_name = self.clean_value(
                    row[column_map["student_name"]]
                )

                school_name = self.clean_value(
                    row[column_map["school"]]
                )

                # ---------------------------------
                # VALIDATION
                # ---------------------------------

                if not student_id:

                    self.stdout.write(
                        self.style.WARNING(
                            f"Row {excel_row}: Student ID missing"
                        )
                    )

                    skipped_count += 1
                    continue

                if not student_name:

                    self.stdout.write(
                        self.style.WARNING(
                            f"Row {excel_row}: Student name missing"
                        )
                    )

                    skipped_count += 1
                    continue

                if not school_name:

                    self.stdout.write(
                        self.style.WARNING(
                            f"Row {excel_row}: School missing"
                        )
                    )

                    skipped_count += 1
                    continue

                # ---------------------------------
                # FIND SCHOOL
                # ---------------------------------

                school = School.objects.filter(
                    name__iexact=school_name
                ).first()

                if not school:

                    self.stdout.write(
                        self.style.ERROR(
                            f"Row {excel_row}: "
                            f"School '{school_name}' not found"
                        )
                    )

                    error_count += 1
                    continue

                # ---------------------------------
                # CLASS
                # ---------------------------------

                class_obj = None

                if "class" in column_map:

                    class_name = self.clean_value(
                        row[column_map["class"]]
                    )

                    section = ""

                    if "section" in column_map:

                        section = self.clean_value(
                            row[column_map["section"]]
                        )

                    # Convert 6.0 -> 6
                    if class_name.endswith(".0"):

                        class_name = class_name[:-2]

                    if class_name:

                        class_obj, class_created = (
                            SchoolClass.objects.get_or_create(
                                school=school,
                                name=class_name,
                                section=section
                            )
                        )

                        if class_created:

                            class_created_count += 1

                # ---------------------------------
                # USERNAME
                # ---------------------------------

                username = f"student_{student_id}"

                # ---------------------------------
                # FIND USER
                # ---------------------------------

                user = User.objects.filter(
                    username=username
                ).first()

                # ---------------------------------
                # NAME
                # ---------------------------------

                name_parts = student_name.split()

                first_name = name_parts[0]

                last_name = ""

                if len(name_parts) > 1:

                    last_name = " ".join(
                        name_parts[1:]
                    )

                # ---------------------------------
                # EMAIL
                # ---------------------------------

                email = ""

                if "email" in column_map:

                    email = self.clean_value(
                        row[column_map["email"]]
                    )

                # ---------------------------------
                # CREATE USER
                # ---------------------------------

                if user is None:

                    user = User.objects.create_user(
                        username=username,
                        password="Student@123",
                        first_name=first_name,
                        last_name=last_name,
                        email=email
                    )

                    user.role = "student"

                    user.save()

                else:

                    # Update basic user information
                    user.first_name = first_name
                    user.last_name = last_name

                    if email:

                        user.email = email

                    user.role = "student"

                    user.save()

                # ---------------------------------
                # HELPER
                # ---------------------------------

                def value(field):

                    if field not in column_map:

                        return ""

                    return self.clean_value(
                        row[column_map[field]]
                    )

                # ---------------------------------
                # STUDENT DATA
                # ---------------------------------

                student_data = {

                    "user": user,

                    "school": school,

                    "class_section": class_obj,

                    "father_name": value(
                        "father_name"
                    ),

                    "mother_name": value(
                        "mother_name"
                    ),

                    "mobile_no": value(
                        "mobile_no"
                    ),

                    "alternate_mobile": value(
                        "alternate_mobile"
                    ),

                    "date_of_birth": self.get_date(
                        row[column_map["date_of_birth"]]
                    ) if "date_of_birth" in column_map else None,

                    "gender": value(
                        "gender"
                    ),

                    "email": email,

                    "address": value(
                        "address"
                    ),

                    "caste": value(
                        "caste"
                    ),

                    "fees": self.get_fee(
                        row[column_map["fees"]]
                    ) if "fees" in column_map else 0,

                    "transport": value(
                        "transport"
                    ),

                    "hostel": value(
                        "hostel"
                    ),

                    "subject": value(
                        "subject"
                    ),

                    "admission_date": self.get_date(
                        row[column_map["admission_date"]]
                    ) if "admission_date" in column_map else None,
                }

                # ---------------------------------
                # CREATE / UPDATE STUDENT
                # ---------------------------------

                student, created = (
                    Student.objects.update_or_create(
                        admission_number=student_id,
                        defaults=student_data
                    )
                )

                if created:

                    created_count += 1

                else:

                    updated_count += 1

                # ---------------------------------
                # PROGRESS
                # ---------------------------------

                if (
                    (created_count + updated_count)
                    % 50 == 0
                ):

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Processed "
                            f"{created_count + updated_count}"
                            f"/{total_rows} students..."
                        )
                    )

            except Exception as e:

                error_count += 1

                self.stdout.write(
                    self.style.ERROR(
                        f"Row {excel_row} ERROR: {e}"
                    )
                )

        # -----------------------------------------
        # FINAL RESULT
        # -----------------------------------------

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "=========================================="
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "       STUDENT IMPORT COMPLETED"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "=========================================="
            )
        )

        self.stdout.write(
            f"Total Excel Rows    : {total_rows}"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"New Students        : {created_count}"
            )
        )

        self.stdout.write(
            f"Updated Students    : {updated_count}"
        )

        self.stdout.write(
            f"Skipped Rows        : {skipped_count}"
        )

        self.stdout.write(
            self.style.ERROR(
                f"Errors              : {error_count}"
            )
        )

        self.stdout.write(
            f"Classes Created     : {class_created_count}"
        )

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Default student password: Student@123"
            )
        )