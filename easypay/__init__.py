"""
Django EasyPay - Payment integration for EasyPay (KICC) PG

Provides:
- AbstractPayment model for inheritance
- EasyPayClient for API communication
- PaymentAdminMixin for Django admin
- PaymentViewMixin for view-level client info handling
- Signals for payment lifecycle events

Usage:
    from easypay.models import AbstractPayment, PaymentStatus
    from easypay.client import EasyPayClient
    from easypay.admin import PaymentAdminMixin
    from easypay.views import PaymentViewMixin
    from easypay.utils import get_client_ip, get_user_agent

Requirements:
- Python 3.12+
- Django 5.0+ (Django 6.0+ recommended)
"""

__version__ = "1.0.0"
__author__ = "Suchan An"
__all__ = ["__version__", "__author__"]
