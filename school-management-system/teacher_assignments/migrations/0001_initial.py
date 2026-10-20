from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('schools', '0001_initial'),
        ('academics', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TeacherPermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('permission_key', models.CharField(max_length=50)),
                ('granted_at', models.DateTimeField(auto_now_add=True)),
                ('granted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='granted_teacher_permissions', to=settings.AUTH_USER_MODEL)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='teacher_permissions', to='schools.school')),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='permissions', to='academics.teacher')),
            ],
            options={
                'ordering': ['-granted_at'],
                'constraints': [
                    models.UniqueConstraint(fields=['school', 'teacher', 'permission_key'], name='unique_teacher_permission')
                ],
            },
        ),
        migrations.CreateModel(
            name='ClassSubjectTeacher',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='class_subject_teachers', to='schools.school')),
                ('school_class', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subject_teachers', to='academics.schoolclass')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='class_teachers', to='academics.subject')),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subject_assignments', to='academics.teacher')),
            ],
            options={
                'ordering': ['school_class', 'subject'],
                'constraints': [
                    models.UniqueConstraint(fields=['school_class', 'subject'], name='unique_class_subject_teacher')
                ],
            },
        ),
    ]
