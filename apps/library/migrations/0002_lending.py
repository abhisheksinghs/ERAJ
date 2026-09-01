# Hand-authored. Assumes the library tables are empty (no production data yet),
# so AddField uses the model's own field definition with no backfill default.
# CI runs `makemigrations --check`; regenerate with
# `python manage.py makemigrations library` if it reports drift.
import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100, unique=True)),
            ],
            options={"verbose_name_plural": "categories", "ordering": ("name",)},
        ),
        # --- Book ---
        migrations.AlterModelOptions(name="book", options={"ordering": ("title",)}),
        migrations.AddField(model_name="book", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(model_name="book", name="publisher", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="book", name="published_year", field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(
            model_name="book", name="category",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="books", to="library.category",
            ),
        ),
        migrations.AddField(
            model_name="book", name="tags",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=50), blank=True, default=list, size=None
            ),
        ),
        migrations.AddField(model_name="book", name="shelf_location", field=models.CharField(blank=True, max_length=50)),
        migrations.AddField(model_name="book", name="deleted_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddConstraint(
            model_name="book",
            constraint=models.CheckConstraint(check=models.Q(copies_available__gte=0), name="library_book_available_nonneg"),
        ),
        migrations.AddConstraint(
            model_name="book",
            constraint=models.CheckConstraint(
                check=models.Q(copies_available__lte=models.F("copies_total")),
                name="library_book_available_lte_total",
            ),
        ),
        # --- Member ---
        migrations.AlterModelOptions(name="member", options={"ordering": ("full_name",)}),
        migrations.RemoveField(model_name="member", name="joined_at"),
        migrations.AddField(model_name="member", name="created_at", field=models.DateTimeField(auto_now_add=True)),
        migrations.AddField(model_name="member", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(model_name="member", name="phone", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="member", name="max_books", field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="member", name="deleted_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        # --- Issue ---
        migrations.AlterModelOptions(name="issue", options={"ordering": ("-created_at",)}),
        migrations.RemoveField(model_name="issue", name="issued_at"),
        migrations.AddField(model_name="issue", name="created_at", field=models.DateTimeField(auto_now_add=True)),
        migrations.AddField(model_name="issue", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(model_name="issue", name="due_date", field=models.DateField(default="2026-01-01")),
        migrations.AddField(model_name="issue", name="renewals", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AlterField(model_name="issue", name="due_date", field=models.DateField()),
        migrations.AddConstraint(
            model_name="issue",
            constraint=models.UniqueConstraint(
                condition=models.Q(returned_at__isnull=True),
                fields=("book", "member"),
                name="library_one_open_loan_per_book_member",
            ),
        ),
        # --- Fine ---
        migrations.CreateModel(
            name="Fine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=8)),
                ("reason", models.CharField(default="overdue return", max_length=255)),
                ("paid", models.BooleanField(default=False)),
                ("waived", models.BooleanField(default=False)),
                ("waived_by", models.CharField(blank=True, max_length=255)),
                ("issue", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="fines", to="library.issue")),
                ("member", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="fines", to="library.member")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        # --- Hold ---
        migrations.CreateModel(
            name="Hold",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(
                    choices=[("waiting", "Waiting"), ("ready", "Ready for pickup"),
                             ("fulfilled", "Fulfilled"), ("cancelled", "Cancelled")],
                    default="waiting", max_length=12)),
                ("book", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="holds", to="library.book")),
                ("member", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="holds", to="library.member")),
            ],
            options={"ordering": ("created_at",)},
        ),
        migrations.AddConstraint(
            model_name="hold",
            constraint=models.UniqueConstraint(
                condition=models.Q(status__in=["waiting", "ready"]),
                fields=("book", "member"),
                name="library_one_active_hold_per_book_member",
            ),
        ),
    ]
