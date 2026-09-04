import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("hr", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Payslip",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("period", models.DateField(help_text="First of the month this payslip covers")),
                ("basic_salary", models.DecimalField(decimal_places=2, max_digits=10)),
                ("allowances", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("deductions", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("net_pay", models.DecimalField(decimal_places=2, max_digits=10)),
                ("employee", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="payslips", to="hr.employee")),
            ],
            options={"ordering": ("-period",)},
        ),
        migrations.AddConstraint(
            model_name="payslip",
            constraint=models.UniqueConstraint(
                fields=("employee", "period"), name="payroll_one_payslip_per_employee_per_period"
            ),
        ),
    ]
