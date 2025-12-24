"""
Django Admin Mixin for EasyPay Payment Management.

Provides comprehensive admin functionality for payment operations:
- Status badges with color coding
- Receipt viewing links
- Real-time PG status inquiry
- Payment cancellation actions
- CSV export
- Payment statistics dashboard

Usage:
    from easypay.admin import PaymentAdminMixin

    @admin.register(Payment)
    class PaymentAdmin(PaymentAdminMixin, admin.ModelAdmin):
        list_display = ['id', 'user'] + PaymentAdminMixin.payment_list_display
"""

import csv
import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.contrib import admin, messages
from django.db.models import Count, QuerySet, Sum
from django.db.models.functions import TruncDate
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.html import format_html

from .client import easypay_client
from .exceptions import EasyPayError
from .models import PaymentStatus
from .utils import mask_card_number

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .models import AbstractPayment


class PaymentAdminMixin:
    """
    Admin Mixin for Payment models inheriting from AbstractPayment.

    Provides operational features for payment management including
    status display, receipt links, PG status inquiry, and batch actions.

    Attributes:
        payment_list_display: Fields to add to list_display
        payment_search_fields: Fields for search
        payment_list_filter: Fields for filtering
        payment_readonly_fields: Read-only fields in detail view
    """

    # === List Display Fields ===
    payment_list_display = [
        "status_badge",
        "amount_display",
        "pay_method",
        "card_name",
        "created_at",
        "paid_at",
        "receipt_link",
    ]

    # === Search & Filter ===
    payment_search_fields = ["pg_tid", "auth_id", "card_no"]
    payment_list_filter = ["status", "pay_method", "card_name", "paid_at"]

    # === Readonly Fields (Detail View) ===
    payment_readonly_fields = [
        "pg_tid",
        "auth_id",
        "card_no",
        "paid_at",
        "client_ip",
        "client_user_agent",
        "receipt_link_detail",
        "pg_status_info",
    ]

    # === Admin Actions ===
    actions = [
        "cancel_selected_payments",
        "refresh_transaction_status",
        "export_to_csv",
    ]

    # === Status Badge Colors ===
    STATUS_COLORS = {
        PaymentStatus.PENDING: ("#FFA500", "#FFF3E0"),  # Orange
        PaymentStatus.COMPLETED: ("#4CAF50", "#E8F5E9"),  # Green
        PaymentStatus.FAILED: ("#F44336", "#FFEBEE"),  # Red
        PaymentStatus.CANCELLED: ("#9E9E9E", "#F5F5F5"),  # Gray
        PaymentStatus.REFUNDED: ("#2196F3", "#E3F2FD"),  # Blue
    }

    # =========================================================================
    # Display Methods (list_display)
    # =========================================================================

    @admin.display(description="상태")
    def status_badge(self, obj: "AbstractPayment") -> str:
        """
        Display payment status as a colored badge.

        Colors:
            - PENDING: Orange
            - COMPLETED: Green
            - FAILED: Red
            - CANCELLED: Gray
            - REFUNDED: Blue
        """
        text_color, bg_color = self.STATUS_COLORS.get(
            obj.status, ("#000000", "#FFFFFF")
        )
        return format_html(
            '<span style="'
            "background-color: {}; "
            "color: {}; "
            "padding: 4px 8px; "
            "border-radius: 4px; "
            "font-size: 11px; "
            "font-weight: bold;"
            '">{}</span>',
            bg_color,
            text_color,
            obj.get_status_display(),
        )

    @admin.display(description="금액")
    def amount_display(self, obj: "AbstractPayment") -> str:
        """Display amount with Korean Won formatting."""
        return f"{int(obj.amount):,}원"

    @admin.display(description="영수증")
    def receipt_link(self, obj: "AbstractPayment") -> str:
        """
        Display receipt link button in list view.

        Returns a button that opens the card receipt in a new tab.
        Only shown for payments with pg_tid.
        """
        if obj.pg_tid:
            url = easypay_client.get_receipt_url(obj.pg_tid)
            return format_html(
                '<a href="{}" target="_blank" '
                'style="'
                "background-color: #1976D2; "
                "color: white; "
                "padding: 4px 8px; "
                "border-radius: 4px; "
                "text-decoration: none; "
                "font-size: 11px;"
                '">🧾</a>',
                url,
            )
        return "-"

    # =========================================================================
    # Detail View Methods (readonly_fields)
    # =========================================================================

    @admin.display(description="영수증 보기")
    def receipt_link_detail(self, obj: "AbstractPayment") -> str:
        """
        Display receipt link button in detail view.

        Larger button with text for the detail/change form.
        """
        if obj.pg_tid:
            url = easypay_client.get_receipt_url(obj.pg_tid)
            return format_html(
                '<a href="{}" target="_blank" '
                'style="'
                "display: inline-block; "
                "background-color: #1976D2; "
                "color: white; "
                "padding: 10px 20px; "
                "border-radius: 4px; "
                "text-decoration: none; "
                "font-weight: bold;"
                '">🧾 카드 영수증 보기</a>',
                url,
            )
        return '<span style="color: #999;">결제 전</span>'

    @admin.display(description="PG 실시간 상태")
    def pg_status_info(self, obj: "AbstractPayment") -> str:
        """
        Display real-time PG transaction status.

        Queries EasyPay API to get current transaction status.
        Shows payment status, approval datetime, and cancellation status.
        """
        if not obj.pg_tid:
            return '<span style="color: #999;">결제 전</span>'

        try:
            status = easypay_client.get_transaction_status(obj)
            cancel_status = "취소됨" if status.get("cancelYn") == "Y" else "정상"
            cancel_color = "#F44336" if status.get("cancelYn") == "Y" else "#4CAF50"

            return format_html(
                '<div style="'
                "background: #F5F5F5; "
                "padding: 12px; "
                "border-radius: 4px; "
                "font-family: monospace;"
                '">'
                "<strong>PG 상태:</strong> {}<br>"
                "<strong>승인일시:</strong> {}<br>"
                '<strong>취소여부:</strong> <span style="color: {};">{}</span>'
                "</div>",
                status.get("payStatusNm", "-"),
                status.get("approvalDt", "-"),
                cancel_color,
                cancel_status,
            )
        except EasyPayError as e:
            return format_html(
                '<span style="color: #F44336;">조회 실패: {}</span>',
                e.message,
            )
        except Exception as e:
            return format_html(
                '<span style="color: #F44336;">조회 실패: {}</span>',
                str(e),
            )

    # =========================================================================
    # Admin Actions
    # =========================================================================

    @admin.action(description="선택한 결제 취소 (환불 처리)")
    def cancel_selected_payments(
        self, request: HttpRequest, queryset: QuerySet
    ) -> None:
        """
        Cancel selected payments (full refund).

        Only processes payments that are in COMPLETED status and have pg_tid.
        Fires payment_cancelled signal for each successful cancellation.
        """
        from .signals import payment_cancelled

        # Audit log: cancellation initiated
        logger.warning(
            "Payment cancellation initiated via admin",
            extra={
                "admin_user": request.user.username,
                "admin_user_id": request.user.id,
                "selected_count": queryset.count(),
            },
        )

        cancelled = 0
        errors = []

        # Filter to only completed payments with pg_tid
        eligible = queryset.filter(status=PaymentStatus.COMPLETED, pg_tid__isnull=False)

        for payment in eligible:
            logger.info(
                "Attempting payment cancellation",
                extra={
                    "payment_id": payment.pk,
                    "amount": int(payment.amount),
                    "pg_tid": payment.pg_tid,
                    "admin_user": request.user.username,
                },
            )

            try:
                result = easypay_client.cancel_payment(payment)

                if result.get("resCd") == "0000":
                    payment.status = PaymentStatus.CANCELLED
                    payment.save(update_fields=["status"])

                    # Fire signal
                    payment_cancelled.send(
                        sender=payment.__class__,
                        payment=payment,
                        cancel_type="40",
                        cancel_amount=int(payment.amount),
                        cancel_data=result,
                    )

                    logger.info(
                        "Payment cancelled successfully",
                        extra={
                            "payment_id": payment.pk,
                            "admin_user": request.user.username,
                        },
                    )
                    cancelled += 1
                else:
                    error_msg = result.get("resMsg", "Unknown error")
                    logger.error(
                        "Payment cancellation failed",
                        extra={
                            "payment_id": payment.pk,
                            "error_code": result.get("resCd"),
                            "error_message": error_msg,
                            "admin_user": request.user.username,
                        },
                    )
                    errors.append(f"#{payment.pk}: {error_msg}")

            except EasyPayError as e:
                logger.error(
                    "Payment cancellation failed with exception",
                    extra={
                        "payment_id": payment.pk,
                        "error_code": e.code,
                        "error_message": e.message,
                        "admin_user": request.user.username,
                    },
                )
                errors.append(f"#{payment.pk}: {e.message}")
            except Exception as e:
                logger.exception(
                    "Payment cancellation unexpected error",
                    extra={
                        "payment_id": payment.pk,
                        "admin_user": request.user.username,
                    },
                )
                errors.append(f"#{payment.pk}: {str(e)}")

        # Show messages
        if cancelled:
            self.message_user(
                request,
                f"✅ {cancelled}건 결제 취소 완료",
                messages.SUCCESS,
            )

        if errors:
            self.message_user(
                request,
                f"❌ 취소 실패: {', '.join(errors)}",
                messages.ERROR,
            )

        skipped = queryset.count() - eligible.count()
        if skipped:
            self.message_user(
                request,
                f"⚠️ {skipped}건은 취소 대상이 아닙니다 (완료 상태가 아니거나 PG 거래번호 없음)",
                messages.WARNING,
            )

    @admin.action(description="PG 거래 상태 동기화")
    def refresh_transaction_status(
        self, request: HttpRequest, queryset: QuerySet
    ) -> None:
        """
        Sync local status with PG server status.

        Queries EasyPay API for each payment and updates local status
        if it differs (e.g., cancelled on PG side but not locally).
        """
        # Audit log: status refresh initiated
        logger.info(
            "PG status refresh initiated via admin",
            extra={
                "admin_user": request.user.username,
                "admin_user_id": request.user.id,
                "selected_count": queryset.count(),
            },
        )

        updated = 0
        errors = []

        # Only process payments with pg_tid
        eligible = queryset.filter(pg_tid__isnull=False)

        for payment in eligible:
            try:
                status = easypay_client.get_transaction_status(payment)

                # Check if cancelled on PG side
                if (
                    status.get("cancelYn") == "Y"
                    and payment.status != PaymentStatus.CANCELLED
                ):
                    payment.status = PaymentStatus.CANCELLED
                    payment.save(update_fields=["status"])
                    logger.info(
                        "Payment status synced to cancelled",
                        extra={
                            "payment_id": payment.pk,
                            "admin_user": request.user.username,
                        },
                    )
                    updated += 1

            except EasyPayError as e:
                logger.error(
                    "PG status inquiry failed",
                    extra={
                        "payment_id": payment.pk,
                        "error_code": e.code,
                        "error_message": e.message,
                    },
                )
                errors.append(f"#{payment.pk}: {e.message}")
            except Exception as e:
                logger.exception(
                    "PG status inquiry unexpected error",
                    extra={"payment_id": payment.pk},
                )
                errors.append(f"#{payment.pk}: {str(e)}")

        # Show messages
        if updated:
            self.message_user(
                request,
                f"✅ {updated}건 상태 동기화 완료",
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "ℹ️ 동기화할 변경사항이 없습니다",
                messages.INFO,
            )

        if errors:
            self.message_user(
                request,
                f"❌ 동기화 실패: {', '.join(errors[:5])}{'...' if len(errors) > 5 else ''}",
                messages.ERROR,
            )

    @admin.action(description="CSV 다운로드")
    def export_to_csv(self, request: HttpRequest, queryset: QuerySet) -> HttpResponse:
        """
        Export selected payments to CSV file.

        Includes payment fields for accounting and reporting purposes.
        Note: Sensitive fields (auth_id) are excluded, card numbers are masked.
        """
        # Audit log: CSV export
        logger.info(
            "Payment CSV export via admin",
            extra={
                "admin_user": request.user.username,
                "admin_user_id": request.user.id,
                "exported_count": queryset.count(),
            },
        )

        response = HttpResponse(
            content_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="payments_{date.today()}.csv"'
            },
        )
        response.write("\ufeff")  # UTF-8 BOM for Excel compatibility

        writer = csv.writer(response)
        writer.writerow(
            [
                "ID",
                "상태",
                "금액",
                "결제수단",
                "카드사",
                "카드번호",  # Masked
                "생성일시",
                "결제일시",
                "PG거래번호",
                # auth_id excluded - sensitive PG token
                "클라이언트IP",
            ]
        )

        for payment in queryset:
            writer.writerow(
                [
                    payment.pk,
                    payment.get_status_display(),
                    int(payment.amount),
                    payment.pay_method,
                    payment.card_name,
                    mask_card_number(payment.card_no),  # PCI-DSS: mask card number
                    payment.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if payment.created_at
                    else "",
                    payment.paid_at.strftime("%Y-%m-%d %H:%M:%S")
                    if payment.paid_at
                    else "",
                    payment.pg_tid,
                    # auth_id excluded - sensitive PG token
                    payment.client_ip or "",
                ]
            )

        return response

    # =========================================================================
    # Statistics Methods
    # =========================================================================

    def get_payment_statistics(self, queryset: QuerySet) -> dict:
        """
        Generate payment statistics for dashboard display.

        Args:
            queryset: QuerySet of payments to analyze

        Returns:
            dict containing:
                - today: Today's count and total
                - this_week: This week's count and total
                - this_month: This month's count and total
                - by_status: Breakdown by payment status
                - by_method: Breakdown by payment method
                - daily_trend: Last 7 days daily totals
        """
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_start = today.replace(day=1)

        # Completed payments only for revenue stats
        completed = queryset.filter(status=PaymentStatus.COMPLETED)

        def get_period_stats(qs, start_date, end_date=None):
            filtered = qs.filter(paid_at__date__gte=start_date)
            if end_date:
                filtered = filtered.filter(paid_at__date__lte=end_date)
            agg = filtered.aggregate(count=Count("id"), total=Sum("amount"))
            return {
                "count": agg["count"] or 0,
                "total": int(agg["total"] or 0),
            }

        return {
            "today": get_period_stats(completed, today),
            "this_week": get_period_stats(completed, week_ago),
            "this_month": get_period_stats(completed, month_start),
            "by_status": list(
                queryset.values("status").annotate(count=Count("id")).order_by("-count")
            ),
            "by_method": list(
                completed.values("pay_method")
                .annotate(count=Count("id"), total=Sum("amount"))
                .order_by("-total")
            ),
            "daily_trend": list(
                completed.filter(paid_at__date__gte=week_ago)
                .annotate(date=TruncDate("paid_at"))
                .values("date")
                .annotate(total=Sum("amount"), count=Count("id"))
                .order_by("date")
            ),
        }

    def changelist_view(
        self, request: HttpRequest, extra_context: dict | None = None
    ) -> HttpResponse:
        """
        Override changelist_view to add payment statistics.

        Adds 'payment_stats' to the template context for dashboard display.
        """
        extra_context = extra_context or {}

        # Get queryset for statistics
        try:
            qs = self.get_queryset(request)
            extra_context["payment_stats"] = self.get_payment_statistics(qs)
        except Exception:
            # Don't break admin if statistics fail
            extra_context["payment_stats"] = None

        return super().changelist_view(request, extra_context=extra_context)
