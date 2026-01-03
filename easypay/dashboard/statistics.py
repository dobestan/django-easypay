"""
Dashboard statistics calculations.

Extends the base payment statistics with date range filtering,
refund metrics, and chart-ready data formats.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypedDict

from django.db.models import Avg, Count, Q, QuerySet, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from easypay.models import PaymentStatus

if TYPE_CHECKING:
    pass


class SummaryCard(TypedDict):
    """Summary card data structure."""

    value: int | Decimal
    formatted: str
    change: float | None
    trend: str  # 'up' | 'down' | 'neutral'


class DailyData(TypedDict):
    """Daily trend data point."""

    date: str
    revenue: int
    count: int


class StatusData(TypedDict):
    """Status breakdown data point."""

    status: str
    label: str
    count: int
    color: str


class MethodData(TypedDict):
    """Payment method breakdown data point."""

    method: str
    label: str
    count: int
    revenue: int


class ComparisonData(TypedDict):
    """Period comparison data point."""

    label: str
    current: int
    previous: int


class DashboardStats(TypedDict):
    """Complete dashboard statistics."""

    summary: dict[str, SummaryCard]
    charts: dict[str, list[Any]]
    comparison: list[ComparisonData]
    meta: dict[str, str]


# Payment method code to label mapping
PAYMENT_METHOD_LABELS: dict[str, str] = {
    "11": "카드",
    "21": "계좌이체",
    "31": "휴대폰",
}

# Status colors for charts (matching admin badge colors)
STATUS_COLORS: dict[str, str] = {
    PaymentStatus.PENDING: "#FFA500",  # Orange
    PaymentStatus.COMPLETED: "#4CAF50",  # Green
    PaymentStatus.FAILED: "#F44336",  # Red
    PaymentStatus.CANCELLED: "#9E9E9E",  # Gray
    PaymentStatus.REFUNDED: "#2196F3",  # Blue
}


def parse_date_range(
    date_range: str,
    start_date_str: str | None = None,
    end_date_str: str | None = None,
) -> tuple[date, date]:
    """
    Parse date range string to start and end dates.

    Args:
        date_range: One of 'today', '7d', '30d', '90d', 'custom'
        start_date_str: Custom start date (ISO format) when date_range='custom'
        end_date_str: Custom end date (ISO format) when date_range='custom'

    Returns:
        Tuple of (start_date, end_date)
    """
    today = timezone.now().date()

    if date_range == "custom" and start_date_str and end_date_str:
        try:
            start = date.fromisoformat(start_date_str)
            end = date.fromisoformat(end_date_str)
            # Validate: start <= end, not in future, not more than 1 year
            if start > end:
                start, end = end, start
            if end > today:
                end = today
            if (end - start).days > 365:
                start = end - timedelta(days=365)
            return start, end
        except ValueError:
            # Invalid date format, fall back to default
            pass

    if date_range == "today":
        return today, today
    elif date_range == "7d":
        return today - timedelta(days=6), today
    elif date_range == "month":
        return date(today.year, today.month, 1), today
    elif date_range == "30d":
        return today - timedelta(days=29), today
    elif date_range == "90d":
        return today - timedelta(days=89), today
    else:
        return date(today.year, today.month, 1), today


def get_previous_period(start_date: date, end_date: date) -> tuple[date, date]:
    """
    Calculate the previous period for comparison.

    Args:
        start_date: Current period start
        end_date: Current period end

    Returns:
        Tuple of (previous_start, previous_end)
    """
    period_days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    return previous_start, previous_end


def calculate_change(current: int | Decimal, previous: int | Decimal) -> tuple[float | None, str]:
    """
    Calculate percentage change between periods.

    Returns:
        Tuple of (change_percent, trend)
    """
    if previous == 0:
        if current > 0:
            return None, "up"
        return None, "neutral"

    change = float((current - previous) / previous * 100)
    trend = "up" if change > 0 else "down" if change < 0 else "neutral"
    return round(change, 1), trend


def format_currency(value: int | Decimal) -> str:
    """Format value as Korean Won currency."""
    return f"₩{int(value):,}"


class CalendarDayData(TypedDict):
    """Calendar day data point."""

    date: str
    day: int
    revenue: int
    count: int


def get_payment_calendar_data(
    queryset: QuerySet,
    year: int,
    month: int,
) -> list[CalendarDayData]:
    """
    Get calendar data for a specific month.

    Args:
        queryset: Base queryset of payments
        year: Year
        month: Month (1-12)

    Returns:
        List of daily data for the calendar
    """
    from calendar import monthrange

    start_date = date(year, month, 1)
    _, last_day = monthrange(year, month)
    end_date = date(year, month, last_day)

    monthly_qs = queryset.filter(
        status=PaymentStatus.COMPLETED,
        paid_at__date__gte=start_date,
        paid_at__date__lte=end_date,
    )

    daily_qs = (
        monthly_qs.annotate(date=TruncDate("paid_at"))
        .values("date")
        .annotate(
            revenue=Sum("amount"),
            count=Count("id"),
        )
        .order_by("date")
    )

    daily_dict = {item["date"]: item for item in daily_qs}

    calendar_data: list[CalendarDayData] = []
    current_date = start_date
    while current_date <= end_date:
        if current_date in daily_dict:
            item = daily_dict[current_date]
            calendar_data.append(
                {
                    "date": current_date.isoformat(),
                    "day": current_date.day,
                    "revenue": int(item["revenue"] or 0),
                    "count": item["count"],
                }
            )
        else:
            calendar_data.append(
                {
                    "date": current_date.isoformat(),
                    "day": current_date.day,
                    "revenue": 0,
                    "count": 0,
                }
            )
        current_date += timedelta(days=1)

    return calendar_data


def get_dashboard_statistics(
    queryset: QuerySet,
    date_range: str = "7d",
    start_date_str: str | None = None,
    end_date_str: str | None = None,
    include_comparison: bool = True,
) -> DashboardStats:
    """
    Calculate comprehensive dashboard statistics.

    Args:
        queryset: Base queryset of payments
        date_range: Date range filter ('today', '7d', '30d', '90d', 'custom')
        start_date_str: Custom start date (ISO format) when date_range='custom'
        end_date_str: Custom end date (ISO format) when date_range='custom'
        include_comparison: Include previous period comparison data

    Returns:
        DashboardStats containing summary cards, chart data, and metadata
    """
    start_date, end_date = parse_date_range(date_range, start_date_str, end_date_str)
    prev_start, prev_end = get_previous_period(start_date, end_date)

    # Filter queryset to date range (using paid_at for completed, created_at for others)
    current_qs = queryset.filter(
        Q(paid_at__date__gte=start_date, paid_at__date__lte=end_date)
        | Q(paid_at__isnull=True, created_at__date__gte=start_date, created_at__date__lte=end_date)
    )

    previous_qs = queryset.filter(
        Q(paid_at__date__gte=prev_start, paid_at__date__lte=prev_end)
        | Q(paid_at__isnull=True, created_at__date__gte=prev_start, created_at__date__lte=prev_end)
    )

    # Completed payments for revenue calculations
    current_completed = current_qs.filter(status=PaymentStatus.COMPLETED)
    previous_completed = previous_qs.filter(status=PaymentStatus.COMPLETED)

    # Refunded/cancelled payments
    current_refunds = current_qs.filter(
        status__in=[PaymentStatus.CANCELLED, PaymentStatus.REFUNDED]
    )
    previous_refunds = previous_qs.filter(
        status__in=[PaymentStatus.CANCELLED, PaymentStatus.REFUNDED]
    )

    # === Summary Cards ===

    # Total Revenue
    current_revenue = current_completed.aggregate(total=Sum("amount"))["total"] or 0
    previous_revenue = previous_completed.aggregate(total=Sum("amount"))["total"] or 0
    revenue_change, revenue_trend = calculate_change(current_revenue, previous_revenue)

    # Transaction Count
    current_count = current_completed.count()
    previous_count = previous_completed.count()
    count_change, count_trend = calculate_change(current_count, previous_count)

    # Average Transaction Value
    current_avg = current_completed.aggregate(avg=Avg("amount"))["avg"] or 0
    previous_avg = previous_completed.aggregate(avg=Avg("amount"))["avg"] or 0
    avg_change, avg_trend = calculate_change(int(current_avg), int(previous_avg))

    # Refund Count
    current_refund_count = current_refunds.count()
    previous_refund_count = previous_refunds.count()
    refund_change, refund_trend = calculate_change(current_refund_count, previous_refund_count)
    # Invert trend for refunds (fewer refunds = good)
    if refund_trend == "up":
        refund_trend = "down"
    elif refund_trend == "down":
        refund_trend = "up"

    summary: dict[str, SummaryCard] = {
        "total_revenue": {
            "value": int(current_revenue),
            "formatted": format_currency(current_revenue),
            "change": revenue_change,
            "trend": revenue_trend,
        },
        "transaction_count": {
            "value": current_count,
            "formatted": f"{current_count:,}건",
            "change": count_change,
            "trend": count_trend,
        },
        "average_value": {
            "value": int(current_avg),
            "formatted": format_currency(current_avg),
            "change": avg_change,
            "trend": avg_trend,
        },
        "refund_count": {
            "value": current_refund_count,
            "formatted": f"{current_refund_count:,}건",
            "change": refund_change,
            "trend": refund_trend,
        },
    }

    # === Chart Data ===

    # Daily Trend (completed payments by date)
    daily_trend_qs = (
        current_completed.annotate(date=TruncDate("paid_at"))
        .values("date")
        .annotate(revenue=Sum("amount"), count=Count("id"))
        .order_by("date")
    )

    # Fill in missing dates with zeros
    daily_trend: list[DailyData] = []
    daily_dict = {item["date"]: item for item in daily_trend_qs}

    current_date = start_date
    while current_date <= end_date:
        if current_date in daily_dict:
            daily_trend.append(
                {
                    "date": current_date.isoformat(),
                    "revenue": int(daily_dict[current_date]["revenue"] or 0),
                    "count": daily_dict[current_date]["count"],
                }
            )
        else:
            daily_trend.append(
                {
                    "date": current_date.isoformat(),
                    "revenue": 0,
                    "count": 0,
                }
            )
        current_date += timedelta(days=1)

    # Status Breakdown (all statuses in current period)
    status_qs = current_qs.values("status").annotate(count=Count("id")).order_by("-count")

    by_status: list[StatusData] = []
    status_labels = dict(PaymentStatus.choices)
    for item in status_qs:
        status: str = item["status"]
        label = status_labels.get(status)
        color = STATUS_COLORS.get(status)
        by_status.append(
            {
                "status": status,
                "label": str(label) if label else status,
                "count": item["count"],
                "color": color if color else "#999999",
            }
        )

    # Payment Method Breakdown (completed only)
    method_qs = (
        current_completed.exclude(pay_method_type_code="")
        .values("pay_method_type_code")
        .annotate(count=Count("id"), revenue=Sum("amount"))
        .order_by("-revenue")
    )

    by_method: list[MethodData] = []
    for item in method_qs:
        method: str = item["pay_method_type_code"]
        by_method.append(
            {
                "method": method,
                "label": PAYMENT_METHOD_LABELS.get(method, method),
                "count": item["count"],
                "revenue": int(item["revenue"] or 0),
            }
        )

    comparison: list[ComparisonData] = []
    if include_comparison:
        comparison = [
            {
                "label": "매출",
                "current": int(current_revenue),
                "previous": int(previous_revenue),
            },
            {
                "label": "건수",
                "current": current_count,
                "previous": previous_count,
            },
            {
                "label": "평균금액",
                "current": int(current_avg),
                "previous": int(previous_avg),
            },
            {
                "label": "환불/취소",
                "current": current_refund_count,
                "previous": previous_refund_count,
            },
        ]

    return {
        "summary": summary,
        "charts": {
            "daily_trend": daily_trend,
            "by_status": by_status,
            "by_method": by_method,
        },
        "comparison": comparison,
        "meta": {
            "date_range": date_range if date_range != "custom" else "custom",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "prev_start_date": prev_start.isoformat(),
            "prev_end_date": prev_end.isoformat(),
        },
    }
