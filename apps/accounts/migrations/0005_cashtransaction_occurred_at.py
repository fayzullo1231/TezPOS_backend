from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_cashtransaction"),
    ]

    operations = [
        migrations.AddField(
            model_name="cashtransaction",
            name="occurred_at",
            field=models.DateTimeField(default=timezone.now),
        ),
        migrations.AddField(
            model_name="cashtransaction",
            name="party_type",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="cashtransaction",
            name="party_name",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
