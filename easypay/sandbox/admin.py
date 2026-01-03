"""
Django Admin for Sandbox Payment model.

Provides admin interface for testing and debugging payment flows.
Only useful when DEBUG=True.
"""

from django.contrib import admin

from easypay.admin import PaymentAdminMixin
from easypay.dashboard import PaymentStatisticsMixin

from .models import SandboxPayment


@admin.register(SandboxPayment)
class SandboxPaymentAdmin(PaymentStatisticsMixin, PaymentAdminMixin, admin.ModelAdmin):
    """
    Admin for SandboxPayment model.

    Inherits all functionality from PaymentAdminMixin:
    - Status badges with color coding
    - Receipt viewing links
    - Real-time PG status inquiry
    - Payment cancellation actions
    - CSV export
    - Payment statistics dashboard
    """

    list_display = [
        "order_id",
        "goods_name",
    ] + PaymentAdminMixin.payment_list_display

    search_fields = ["order_id", "goods_name"] + PaymentAdminMixin.payment_search_fields
    list_filter = PaymentAdminMixin.payment_list_filter
    readonly_fields = PaymentAdminMixin.payment_readonly_fields + ["order_id"]

    fieldsets = (
        (
            "결제 정보",
            {
                "fields": (
                    "order_id",
                    "goods_name",
                    "amount",
                    "status",
                )
            },
        ),
        (
            "PG 정보",
            {
                "fields": (
                    "pg_tid",
                    "auth_id",
                    "pay_method",
                    "card_name",
                    "card_no",
                    "paid_at",
                )
            },
        ),
        (
            "클라이언트 정보",
            {
                "fields": (
                    "client_ip",
                    "client_user_agent",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "PG 조회",
            {
                "fields": (
                    "receipt_link_detail",
                    "pg_status_info",
                ),
            },
        ),
    )

    date_hierarchy = "created_at"
    ordering = ["-created_at"]
