"""
Sandbox module for testing EasyPay integration.

This module provides a simple testing interface for EasyPay payments.
It's designed to work only in DEBUG mode and uses the test MID.

Usage:
    # In your project's urls.py (only for development)
    if settings.DEBUG:
        urlpatterns += [
            path('easypay/sandbox/', include('easypay.sandbox.urls')),
        ]

    # Then visit http://localhost:8000/easypay/sandbox/ to test payments
"""

default_app_config = "easypay.sandbox.apps.EasypaySandboxConfig"
