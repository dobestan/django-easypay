"""
Payment Dashboard for Django Admin.

Provides analytics dashboard with charts and metrics for payment data.

Usage:
    from easypay.admin import PaymentAdminMixin
    from easypay.dashboard import PaymentDashboardMixin

    @admin.register(Payment)
    class PaymentAdmin(PaymentDashboardMixin, PaymentAdminMixin, admin.ModelAdmin):
        pass
"""

from .mixins import PaymentDashboardMixin

__all__ = ["PaymentDashboardMixin"]
