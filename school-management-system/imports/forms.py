from django import forms
from schools.models import School


class ExcelUploadForm(forms.Form):

    school = forms.ModelChoiceField(
        queryset=School.objects.all(),
        label="Select School"
    )

    file = forms.FileField(
        label="Select CSV / Excel File",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".csv,.xlsx,.xls"
            }
        )
    )

    def clean_file(self):
        file = self.cleaned_data["file"]

        allowed = [".csv", ".xlsx", ".xls"]

        filename = file.name.lower()

        if not any(filename.endswith(ext) for ext in allowed):
            raise forms.ValidationError(
                "Only CSV, XLSX or XLS files are allowed."
            )

        return file