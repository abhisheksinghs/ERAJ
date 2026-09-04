import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Item",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("name", models.CharField(max_length=255)),
                ("sku", models.CharField(max_length=50, unique=True)),
                ("category", models.CharField(blank=True, max_length=100)),
                ("quantity_total", models.PositiveIntegerField(default=1)),
                ("quantity_available", models.PositiveIntegerField(default=1)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="IssueRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("issued_to", models.CharField(max_length=255)),
                ("returned_at", models.DateTimeField(blank=True, null=True)),
                ("item", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="issues", to="inventory.item")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="item",
            constraint=models.CheckConstraint(check=models.Q(quantity_available__gte=0), name="inventory_item_available_nonneg"),
        ),
        migrations.AddConstraint(
            model_name="item",
            constraint=models.CheckConstraint(
                check=models.Q(quantity_available__lte=models.F("quantity_total")),
                name="inventory_item_available_lte_total",
            ),
        ),
    ]
