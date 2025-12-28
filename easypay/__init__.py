"""
Django EasyPay - Payment integration for EasyPay (KICC) PG

Provides:
- AbstractPayment model for inheritance
- EasyPayClient for API communication
- PaymentAdminMixin for Django admin
- Signals for payment lifecycle events

Requirements:
- Python 3.12+
- Django 5.0+ (Django 6.0+ recommended)
"""

__version__ = "1.0.0"
__author__ = "Suhan Bae"
__all__ = ["__version__", "__author__"]
