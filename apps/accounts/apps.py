from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        # Registers the OpenAPI auth extension (import side effect).
        from apps.accounts import schema  # noqa: F401
