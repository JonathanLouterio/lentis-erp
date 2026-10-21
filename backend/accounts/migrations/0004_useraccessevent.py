from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_user_theme")]
    operations = [
        migrations.CreateModel(
            name="UserAccessEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=24)),
                ("changes", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name="performed_access_events", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name="access_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-id"], "verbose_name": "Histórico de acesso do usuário",
                     "verbose_name_plural": "Históricos de acesso dos usuários"},
        ),
    ]
