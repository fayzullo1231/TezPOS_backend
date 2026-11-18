from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_shift_close_and_defaults"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="employee",
            index=models.Index(
                fields=["tenant", "is_active", "name"],
                name="emp_tenant_active_name_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=("tenant", "name"),
                name="uniq_active_employee_name_per_tenant",
            ),
        ),
    ]
