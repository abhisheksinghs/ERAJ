# Hand-authored. Assumes the hostel tables are empty (no production data yet).
# CI runs `makemigrations --check`; regenerate with
# `python manage.py makemigrations hostel` if it reports drift.
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hostel", "0001_initial"),
    ]

    operations = [
        # --- Room ---
        migrations.AlterModelOptions(name="room", options={"ordering": ("number",)}),
        migrations.AddField(model_name="room", name="created_at", field=models.DateTimeField(auto_now_add=True)),
        migrations.AddField(model_name="room", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(model_name="room", name="deleted_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AlterField(model_name="room", name="number", field=models.CharField(max_length=20, unique=True)),
        migrations.AlterField(model_name="room", name="capacity", field=models.PositiveSmallIntegerField(default=2)),
        migrations.AddField(
            model_name="room", name="room_type",
            field=models.CharField(
                choices=[("single", "Single"), ("double", "Double"), ("dorm", "Dormitory")],
                default="double", max_length=10),
        ),
        migrations.AddField(
            model_name="room", name="gender",
            field=models.CharField(
                choices=[("male", "Male"), ("female", "Female"), ("any", "Any")],
                default="any", max_length=6),
        ),
        migrations.AddField(model_name="room", name="floor", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(
            model_name="room", name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("maintenance", "Under maintenance"),
                         ("decommissioned", "Decommissioned")],
                default="active", max_length=16),
        ),
        # --- Resident ---
        migrations.AlterModelOptions(name="resident", options={"ordering": ("full_name",)}),
        migrations.RemoveField(model_name="resident", name="room"),
        migrations.AddField(model_name="resident", name="created_at", field=models.DateTimeField(auto_now_add=True)),
        migrations.AddField(model_name="resident", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(model_name="resident", name="email", field=models.EmailField(blank=True, max_length=254)),
        migrations.AddField(model_name="resident", name="phone", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="resident", name="guardian_name", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="resident", name="guardian_phone", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="resident", name="deleted_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        # --- Allocation ---
        migrations.CreateModel(
            name="Allocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("check_in_date", models.DateField(default=django.utils.timezone.localdate)),
                ("check_out_date", models.DateField(blank=True, null=True)),
                ("resident", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="allocations", to="hostel.resident")),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="allocations", to="hostel.room")),
            ],
            options={"ordering": ("-check_in_date",)},
        ),
        migrations.AddConstraint(
            model_name="allocation",
            constraint=models.UniqueConstraint(
                condition=models.Q(check_out_date__isnull=True),
                fields=("resident",),
                name="hostel_one_active_allocation_per_resident",
            ),
        ),
        # --- Waitlist ---
        migrations.CreateModel(
            name="Waitlist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(
                    choices=[("waiting", "Waiting"), ("offered", "Offered"),
                             ("fulfilled", "Fulfilled"), ("cancelled", "Cancelled")],
                    default="waiting", max_length=10)),
                ("resident", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="waitlist_entries", to="hostel.resident")),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="waitlist", to="hostel.room")),
            ],
            options={"ordering": ("created_at",)},
        ),
        migrations.AddConstraint(
            model_name="waitlist",
            constraint=models.UniqueConstraint(
                condition=models.Q(status__in=["waiting", "offered"]),
                fields=("resident", "room"),
                name="hostel_one_active_waitlist_entry_per_resident_room",
            ),
        ),
        # --- MaintenanceTicket ---
        migrations.CreateModel(
            name="MaintenanceTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("summary", models.CharField(max_length=255)),
                ("details", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("open", "Open"), ("closed", "Closed")], default="open", max_length=6)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="maintenance_tickets", to="hostel.room")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
