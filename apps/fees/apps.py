from django.apps import AppConfig


class FeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fees"
    label = "fees"

    def ready(self):
        from apps.fees import signals  # noqa: F401
