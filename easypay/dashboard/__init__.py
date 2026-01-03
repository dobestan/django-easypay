"""
Payment Dashboard for Django Admin.

Provides analytics dashboard with charts and metrics for payment data.

Usage:
    from easypay.admin import PaymentAdminMixin
    from easypay.dashboard import PaymentStatisticsMixin

    @admin.register(Payment)
    class PaymentAdmin(PaymentStatisticsMixin, PaymentAdminMixin, admin.ModelAdmin):
        pass
"""

from .mixins import PaymentStatisticsMixin

__all__ = ["PaymentStatisticsMixin"]
