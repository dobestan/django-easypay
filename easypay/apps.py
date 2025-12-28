from django.apps import AppConfig


class EasyPayConfig(AppConfig):
    """Django app configuration for EasyPay."""

    name = "easypay"
    verbose_name = "EasyPay Payment"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """Import signals when the app is ready."""
        from . import signals  # noqa: F401
