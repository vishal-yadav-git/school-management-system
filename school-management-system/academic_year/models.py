from django.core.exceptions import ValidationError
from django.db import models


class AcademicYear(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="academic_years",
    )
    name = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"],
                name="unique_academic_year_school_name",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="academic_year_end_date_after_start_date",
            ),
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(is_current=True),
                name="unique_current_academic_year_per_school",
            ),
        ]
        ordering = ["-start_date", "name"]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "End date must be after start date."})

    def __str__(self):
        return f"{self.name} ({self.school.name})"
