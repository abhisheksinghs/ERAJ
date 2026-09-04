import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="FeeStructure",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("term", models.CharField(blank=True, max_length=100)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("due_date", models.DateField(blank=True, null=True)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("payer_name", models.CharField(max_length=255)),
                ("payer_reference", models.CharField(blank=True, max_length=100)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("receipt_no", models.CharField(max_length=30, unique=True)),
                ("fee_structure", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="fees.feestructure")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
