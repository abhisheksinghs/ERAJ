import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Student",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("full_name", models.CharField(max_length=255)),
                ("roll_no", models.CharField(max_length=50, unique=True)),
                ("class_section", models.CharField(blank=True, max_length=50)),
            ],
            options={"ordering": ("full_name",)},
        ),
        migrations.CreateModel(
            name="Subject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="ExamResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("exam_name", models.CharField(help_text='e.g. "Midterm 2026"', max_length=100)),
                ("marks_obtained", models.DecimalField(decimal_places=2, max_digits=6)),
                ("max_marks", models.DecimalField(decimal_places=2, default=100, max_digits=6)),
                ("student", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="results", to="exam.student")),
                ("subject", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="results", to="exam.subject")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="examresult",
            constraint=models.UniqueConstraint(
                fields=("student", "subject", "exam_name"), name="exam_one_result_per_student_subject_exam"
            ),
        ),
    ]
