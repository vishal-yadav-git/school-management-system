import os
import uuid
import pandas as pd

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404

from academics.models import Student, SchoolClass
from schools.models import School

from .forms import ExcelUploadForm


User = get_user_model()


# =========================================================
# BASIC HELPERS
# =========================================================

def clean_value(value):

    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_column_name(column):

    column = str(column).strip().lower()

    column = (
        column
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )

    aliases = {

        "studentid": "student_id",
        "student_id": "student_id",
        "student_no": "student_id",
        "student_number": "student_id",

        "studentname": "student_name",
        "student_name": "student_name",
        "name": "student_name",

        "father": "father_name",
        "fathername": "father_name",
        "father_name": "father_name",

        "mother": "mother_name",
        "mothername": "mother_name",
        "mother_name": "mother_name",

        "mobile": "mobile_no",
        "mobile_number": "mobile_no",
        "mobile_no": "mobile_no",

        "alt_mobile": "alt_mobile_no",
        "alternate_mobile": "alt_mobile_no",
        "alternate_mobile_no": "alt_mobile_no",
        "alt_mobile_no": "alt_mobile_no",

        "dob": "date_of_birth",
        "dateofbirth": "date_of_birth",
        "date_of_birth": "date_of_birth",

        "admissiondate": "admission_date",
        "admission_date": "admission_date",

        "class_name": "class",
        "class": "class",

        "section_name": "section",
        "section": "section",

        "school_name": "school",
        "school": "school",

        "subject_name": "subject",
        "subject": "subject",
    }

    return aliases.get(column, column)


def find_header_row(dataframe):

    for index in range(min(20, len(dataframe))):

        row_values = [
            normalize_column_name(value)
            for value in dataframe.iloc[index].tolist()
        ]

        if (
            "student_id" in row_values
            and
            "student_name" in row_values
        ):
            return index

    return None


# =========================================================
# READ CSV / EXCEL
# =========================================================

def read_uploaded_file(uploaded_file):

    extension = os.path.splitext(
        uploaded_file.name
    )[1].lower()

    # ---------------- CSV ----------------

    if extension == ".csv":

        uploaded_file.seek(0)

        raw_df = pd.read_csv(
            uploaded_file,
            header=None,
            dtype=str
        )

        header_row = find_header_row(raw_df)

        if header_row is None:
            raise ValueError(
                "Student ID aur Student Name ke "
                "headers nahi mile."
            )

        headers = [
            normalize_column_name(value)
            for value in raw_df.iloc[
                header_row
            ].tolist()
        ]

        df = raw_df.iloc[
            header_row + 1:
        ].copy()

        df.columns = headers

        df = df.dropna(
            how="all"
        )

        return df.fillna("")

    # ---------------- EXCEL ----------------

    if extension in [".xlsx", ".xls"]:

        uploaded_file.seek(0)

        excel_file = pd.ExcelFile(
            uploaded_file
        )

        for sheet_name in excel_file.sheet_names:

            uploaded_file.seek(0)

            raw_df = pd.read_excel(
                uploaded_file,
                sheet_name=sheet_name,
                header=None,
                dtype=str
            )

            header_row = find_header_row(
                raw_df
            )

            if header_row is not None:

                headers = [
                    normalize_column_name(value)
                    for value in raw_df.iloc[
                        header_row
                    ].tolist()
                ]

                df = raw_df.iloc[
                    header_row + 1:
                ].copy()

                df.columns = headers

                df = df.dropna(
                    how="all"
                )

                return df.fillna("")

        raise ValueError(
            "Excel ki kisi bhi sheet mein "
            "Student ID aur Student Name "
            "columns nahi mile."
        )

    raise ValueError(
        "Sirf CSV, XLSX aur XLS files allowed hain."
    )


# =========================================================
# DATE
# =========================================================

def convert_date(value):

    value = clean_value(value)

    if not value:
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


# =========================================================
# FEES
# =========================================================

def convert_fee(value):

    value = clean_value(value)

    if not value:
        return 0

    try:

        value = (
            value
            .replace(",", "")
            .replace("₹", "")
            .strip()
        )

        return float(value)

    except Exception:

        return 0


# =========================================================
# NAME
# =========================================================

def split_name(name):

    name = clean_value(name)

    if not name:
        return "", ""

    parts = name.split()

    return (
        parts[0],
        " ".join(parts[1:])
    )


# =========================================================
# UPLOAD + PREVIEW
# =========================================================

@login_required
def import_excel(request):

    if not request.user.is_superuser:

        messages.error(
            request,
            "You are not authorized to import data."
        )

        return redirect("dashboard")

    if request.method == "POST":

        form = ExcelUploadForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            school = form.cleaned_data["school"]

            uploaded_file = form.cleaned_data["file"]

            try:

                # Read Excel / CSV
                df = read_uploaded_file(
                    uploaded_file
                )

                # Required columns
                if "student_id" not in df.columns:

                    raise ValueError(
                        "Student ID column nahi mila."
                    )

                if "student_name" not in df.columns:

                    raise ValueError(
                        "Student Name column nahi mila."
                    )

                # ------------------------------------------------
                # SCHOOL VALIDATION
                # ------------------------------------------------

                if "school" in df.columns:

                    file_schools = set()

                    for value in df["school"]:

                        value = clean_value(
                            value
                        ).lower()

                        if value:
                            file_schools.add(value)

                    if file_schools:

                        selected_school = (
                            school.name
                            .strip()
                            .lower()
                        )

                        matched = False

                        for file_school in file_schools:

                            if (
                                file_school in selected_school
                                or
                                selected_school in file_school
                            ):
                                matched = True

                        if not matched:

                            raise ValueError(
                                f"File mein school "
                                f"{', '.join(file_schools)} hai, "
                                f"lekin aapne "
                                f"{school.name} select kiya hai."
                            )

                # ------------------------------------------------
                # TEMP FILE
                # ------------------------------------------------

                import_folder = os.path.join(
                    settings.MEDIA_ROOT,
                    "import_temp"
                )

                os.makedirs(
                    import_folder,
                    exist_ok=True
                )

                unique_name = (
                    f"{uuid.uuid4().hex}_"
                    f"{uploaded_file.name}"
                )

                temp_path = os.path.join(
                    import_folder,
                    unique_name
                )

                with open(
                    temp_path,
                    "wb"
                ) as destination:

                    for chunk in uploaded_file.chunks():

                        destination.write(chunk)

                # ------------------------------------------------
                # SIGNED TOKEN
                # ------------------------------------------------

                token_data = {
                    "file": temp_path,
                    "school_id": school.id,
                    "filename": uploaded_file.name,
                }

                token = signing.dumps(
                    token_data
                )

                # ------------------------------------------------
                # PREVIEW
                # ------------------------------------------------

                columns = list(
                    df.columns
                )

                preview_rows = []

                for _, row in df.head(10).iterrows():

                    values = []

                    for column in columns:

                        values.append(
                            clean_value(
                                row.get(
                                    column,
                                    ""
                                )
                            )
                        )

                    preview_rows.append(
                        values
                    )

                return render(
                    request,
                    "imports/import_preview.html",
                    {
                        "school": school,
                        "filename": uploaded_file.name,
                        "total_rows": len(df),
                        "columns": columns,
                        "preview_rows": preview_rows,
                        "import_token": token,
                    }
                )

            except Exception as e:

                messages.error(
                    request,
                    f"File reading failed: {str(e)}"
                )

                return redirect(
                    "import_excel"
                )

    else:

        form = ExcelUploadForm()

    return render(
        request,
        "imports/import_excel.html",
        {
            "form": form
        }
    )


# =========================================================
# CONFIRM IMPORT
# =========================================================

@login_required
def confirm_import(request):

    if not request.user.is_superuser:

        messages.error(
            request,
            "You are not authorized to import data."
        )

        return redirect("dashboard")

    if request.method != "POST":

        return redirect(
            "import_excel"
        )

    token = request.POST.get(
        "import_token"
    )

    if not token:

        messages.error(
            request,
            "Import token missing."
        )

        return redirect(
            "import_excel"
        )

    try:

        data = signing.loads(
            token,
            max_age=3600
        )

    except signing.BadSignature:

        messages.error(
            request,
            "Import request invalid or expired."
        )

        return redirect(
            "import_excel"
        )

    temp_path = data.get(
        "file"
    )

    school_id = data.get(
        "school_id"
    )

    filename = data.get(
        "filename",
        ""
    )

    if not temp_path or not school_id:

        messages.error(
            request,
            "Import information missing."
        )

        return redirect(
            "import_excel"
        )

    school = get_object_or_404(
        School,
        id=school_id
    )

    if not os.path.exists(temp_path):

        messages.error(
            request,
            "Temporary import file not found."
        )

        return redirect(
            "import_excel"
        )

    try:

        # ------------------------------------------------
        # READ FILE
        # ------------------------------------------------

        with open(
            temp_path,
            "rb"
        ) as file:

            class TempFile:

                def __init__(
                    self,
                    file_obj,
                    name
                ):

                    self.file_obj = file_obj
                    self.name = name

                def read(
                    self,
                    *args,
                    **kwargs
                ):

                    return self.file_obj.read(
                        *args,
                        **kwargs
                    )

                def seek(
                    self,
                    *args,
                    **kwargs
                ):

                    return self.file_obj.seek(
                        *args,
                        **kwargs
                    )

            wrapped_file = TempFile(
                file,
                filename
            )

            df = read_uploaded_file(
                wrapped_file
            )

        total = len(df)

        imported = 0

        duplicate = 0

        errors = []

        # ------------------------------------------------
        # DATABASE IMPORT
        # ------------------------------------------------

        with transaction.atomic():

            for index, row in df.iterrows():

                row_number = index + 2

                try:

                    admission_number = clean_value(
                        row.get(
                            "student_id",
                            ""
                        )
                    )

                    student_name = clean_value(
                        row.get(
                            "student_name",
                            ""
                        )
                    )

                    if not admission_number:

                        errors.append(
                            f"Row {row_number}: "
                            "Student ID missing."
                        )

                        continue

                    if not student_name:

                        errors.append(
                            f"Row {row_number}: "
                            "Student Name missing."
                        )

                        continue

                    # Duplicate
                    if Student.objects.filter(
                        admission_number=admission_number
                    ).exists():

                        duplicate += 1

                        continue

                    # User
                    first_name, last_name = split_name(
                        student_name
                    )

                    username = (
                        f"{school.code.lower()}_"
                        f"{admission_number}"
                    )

                    base_username = username

                    counter = 1

                    while User.objects.filter(
                        username=username
                    ).exists():

                        username = (
                            f"{base_username}_"
                            f"{counter}"
                        )

                        counter += 1

                    user = User.objects.create_user(

                        username=username,

                        password="Student@123",

                        first_name=first_name,

                        last_name=last_name,

                        email=clean_value(
                            row.get(
                                "email",
                                ""
                            )
                        ),

                        role="student"
                    )

                    # Class
                    class_name = clean_value(
                        row.get(
                            "class",
                            ""
                        )
                    )

                    section = clean_value(
                        row.get(
                            "section",
                            ""
                        )
                    )

                    school_class = None

                    if class_name:

                        school_class, _ = (
                            SchoolClass.objects.get_or_create(
                                school=school,
                                name=class_name,
                                section=section
                            )
                        )

                    # Student
                    Student.objects.create(

                        user=user,

                        school=school,

                        class_section=school_class,

                        admission_number=admission_number,

                        father_name=clean_value(
                            row.get(
                                "father_name",
                                ""
                            )
                        ),

                        mother_name=clean_value(
                            row.get(
                                "mother_name",
                                ""
                            )
                        ),

                        mobile_no=clean_value(
                            row.get(
                                "mobile_no",
                                ""
                            )
                        ),

                        alternate_mobile=clean_value(
                            row.get(
                                "alt_mobile_no",
                                ""
                            )
                        ),

                        date_of_birth=convert_date(
                            row.get(
                                "date_of_birth",
                                ""
                            )
                        ),

                        gender=clean_value(
                            row.get(
                                "gender",
                                ""
                            )
                        ),

                        email=clean_value(
                            row.get(
                                "email",
                                ""
                            )
                        ),

                        address=clean_value(
                            row.get(
                                "address",
                                ""
                            )
                        ),

                        caste=clean_value(
                            row.get(
                                "caste",
                                ""
                            )
                        ),

                        fees=convert_fee(
                            row.get(
                                "fees",
                                ""
                            )
                        ),

                        transport=clean_value(
                            row.get(
                                "transport",
                                ""
                            )
                        ),

                        hostel=clean_value(
                            row.get(
                                "hostel",
                                ""
                            )
                        ),

                        subject=clean_value(
                            row.get(
                                "subject",
                                ""
                            )
                        ),

                        admission_date=convert_date(
                            row.get(
                                "admission_date",
                                ""
                            )
                        )
                    )

                    imported += 1

                except Exception as e:

                    errors.append(
                        f"Row {row_number}: {str(e)}"
                    )

        # Delete temporary file
        if os.path.exists(temp_path):

            os.remove(temp_path)

        return render(
            request,
            "imports/import_result.html",
            {
                "school": school,
                "filename": filename,
                "total": total,
                "imported": imported,
                "duplicate": duplicate,
                "errors": errors,
            }
        )

    except Exception as e:

        if os.path.exists(temp_path):

            os.remove(temp_path)

        messages.error(
            request,
            f"Import failed: {str(e)}"
        )

        return redirect(
            "import_excel"
        )