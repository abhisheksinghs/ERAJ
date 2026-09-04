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
            name="AttendanceRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("date", models.DateField()),
                ("status", models.CharField(
                    choices=[("present", "Present"), ("absent", "Absent"), ("leave", "Leave")],
                    default="present", max_length=10)),
                ("marked_by", models.CharField(blank=True, max_length=255)),
                ("student", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="attendance_records", to="attendance.student")),
            ],
            options={"ordering": ("-date",)},
        ),
        migrations.AddConstraint(
            model_name="attendancerecord",
            constraint=models.UniqueConstraint(
                fields=("student", "date"), name="attendance_one_record_per_student_per_day"
            ),
        ),
    ]
