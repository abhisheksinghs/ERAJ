import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Route",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("stops", models.TextField(blank=True, help_text="One stop per line")),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="Vehicle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("number", models.CharField(max_length=20, unique=True)),
                ("capacity", models.PositiveSmallIntegerField(default=40)),
                ("route", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="vehicles", to="transport.route")),
            ],
            options={"ordering": ("number",)},
        ),
        migrations.CreateModel(
            name="TransportAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rider_name", models.CharField(max_length=255)),
                ("rider_contact", models.CharField(blank=True, max_length=20)),
                ("pickup_point", models.CharField(blank=True, max_length=255)),
                ("removed_at", models.DateTimeField(blank=True, null=True)),
                ("vehicle", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="assignments", to="transport.vehicle")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
