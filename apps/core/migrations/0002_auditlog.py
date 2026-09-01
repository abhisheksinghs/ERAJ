from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("schema_name", models.CharField(db_index=True, max_length=63)),
                ("actor", models.CharField(blank=True, max_length=255)),
                ("action", models.CharField(db_index=True, max_length=100)),
                ("detail", models.JSONField(blank=True, default=dict)),
            ],
            options={"ordering": ("-at",)},
        ),
    ]
