"""
Django EasyPay - Payment integration for EasyPay (KICC) PG

Provides:
- AbstractPayment model for inheritance
- EasyPayClient for API communication
- PaymentAdminMixin for Django admin
- Signals for payment lifecycle events
"""

__version__ = "1.0.0"
__author__ = "Suhan Bae"

default_app_config = "easypay.apps.EasyPayConfig"
