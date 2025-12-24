"""
Django App configuration for EasyPay Sandbox.
"""

from django.apps import AppConfig


class EasypaySandboxConfig(AppConfig):
    """Configuration for the EasyPay Sandbox app."""

    name = "easypay.sandbox"
    label = "easypay_sandbox"
    verbose_name = "EasyPay Sandbox"
    default_auto_field = "django.db.models.BigAutoField"
