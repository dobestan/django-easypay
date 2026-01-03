# Payment Dashboard

django-easypay provides an optional analytics dashboard for visualizing payment data directly in Django Admin.

## Quick Start

Add `PaymentDashboardMixin` before `PaymentAdminMixin` in your admin class:

```python
from django.contrib import admin
from easypay.admin import PaymentAdminMixin
from easypay.dashboard import PaymentDashboardMixin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(PaymentDashboardMixin, PaymentAdminMixin, admin.ModelAdmin):
    pass
```

Access the dashboard at: `/admin/<app_label>/<model_name>/dashboard/`

## Features

### Summary Cards

Four key metrics displayed at the top:

| Card | Description |
|------|-------------|
| **Total Revenue** | Sum of completed payments in the selected period |
| **Transaction Count** | Number of completed payments |
| **Average Value** | Average payment amount |
| **Refund Count** | Number of cancelled/refunded payments |

Each card shows:
- Current value
- Percentage change vs previous period (same duration)
- Trend indicator (up/down/neutral)

### Revenue Trend Chart

Line chart showing daily revenue and transaction count over the selected period.

- Primary axis: Revenue (KRW)
- Secondary axis: Transaction count
- Hover for detailed values

### Status Breakdown

Doughnut chart showing distribution of payment statuses:
- Completed (green)
- Pending (orange)
- Failed (red)
- Cancelled (gray)
- Refunded (blue)

### Payment Method Breakdown

Horizontal bar chart showing revenue by payment method:
- Card (11)
- Bank Transfer (21)
- Mobile (31)

### Period Comparison Chart

Side-by-side bar chart comparing current period vs previous period:
- Revenue comparison
- Transaction count comparison
- Average value comparison
- Refund count comparison

The previous period is automatically calculated based on the selected date range duration.

## Date Ranges

Select from preset date ranges:

| Range | Description |
|-------|-------------|
| `month` | Current month (default) |
| `today` | Current day only |
| `7d` | Last 7 days |
| `30d` | Last 30 days |
| `90d` | Last 90 days |
| `custom` | Custom date range with calendar picker |

Date range is preserved in URL query parameter (`?range=30d`).

### Custom Date Range Picker

Click "직접선택" to open the calendar picker:
- **Monday-start calendar**: Week starts on Monday (월화수목금토일)
- **Weekend highlighting**: Saturday (blue), Sunday (red)
- **Date input fields**: Manual entry with date inputs
- **Click-to-select**: Click start date, then end date
- **Date validation**: Future dates disabled, auto-swap if reversed

## CSV Export

Download payment data as CSV:

```
GET /admin/<app_label>/<model_name>/dashboard/export/?range=7d
GET /admin/<app_label>/<model_name>/dashboard/export/?range=custom&start_date=2026-01-01&end_date=2026-01-15
```

The CSV includes:
- ID, Order Number, Amount, Status, Payment Method, Created At, Paid At

Click the "CSV 다운로드" button in the date picker section.

## Configuration

Customize the mixin behavior:

```python
class PaymentAdmin(PaymentDashboardMixin, PaymentAdminMixin, admin.ModelAdmin):
    # Change default date range (default: 'month')
    dashboard_default_range = '30d'
    
    # Use custom template
    dashboard_template = 'myapp/custom_dashboard.html'
```

## API Endpoint

The dashboard includes a JSON API for AJAX updates:

```
GET /admin/<app_label>/<model_name>/dashboard/api/?range=7d
```

Response structure:

```json
{
  "summary": {
    "total_revenue": {"value": 1200000, "formatted": "₩1,200,000", "change": 12.5, "trend": "up"},
    "transaction_count": {"value": 42, "formatted": "42건", "change": 8.0, "trend": "up"},
    "average_value": {"value": 28571, "formatted": "₩28,571", "change": -2.3, "trend": "down"},
    "refund_count": {"value": 2, "formatted": "2건", "change": null, "trend": "neutral"}
  },
  "charts": {
    "daily_trend": [
      {"date": "2026-01-01", "revenue": 150000, "count": 5}
    ],
    "by_status": [
      {"status": "completed", "label": "결제완료", "count": 38, "color": "#4CAF50"}
    ],
    "by_method": [
      {"method": "11", "label": "카드", "count": 40, "revenue": 1140000}
    ]
  },
  "comparison": [
    {"label": "매출", "current": 1200000, "previous": 1000000},
    {"label": "건수", "current": 42, "previous": 38},
    {"label": "평균금액", "current": 28571, "previous": 26315},
    {"label": "환불/취소", "current": 2, "previous": 3}
  ],
  "meta": {
    "date_range": "7d",
    "start_date": "2025-12-27",
    "end_date": "2026-01-03",
    "prev_start_date": "2025-12-20",
    "prev_end_date": "2025-12-26"
  }
}
```

For custom date ranges:

```
GET /admin/<app_label>/<model_name>/dashboard/api/?range=custom&start_date=2026-01-01&end_date=2026-01-15
```

## Custom Templates

Override the dashboard template for custom styling:

```python
class PaymentAdmin(PaymentDashboardMixin, PaymentAdminMixin, admin.ModelAdmin):
    dashboard_template = 'payments/dashboard.html'
```

Your template should extend `admin/base_site.html` and include Chart.js:

```html
{% extends "admin/base_site.html" %}
{% load static %}

{% block extrahead %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
{% endblock %}

{% block content %}
<!-- Your dashboard HTML -->
<script>
// Chart initialization using {{ chart_data|safe }}
</script>
{% endblock %}
```

Context variables available:
- `stats`: Dashboard statistics dictionary
- `date_range`: Current date range string
- `date_ranges`: Tuple of valid date range options
- `api_url`: URL to JSON API endpoint
- `chart_data`: JSON-encoded statistics for Chart.js

## Static Files

The dashboard uses these static files:
- `easypay/dashboard/dashboard.css` - Styles
- `easypay/dashboard/dashboard.js` - Chart.js initialization

Include in your project's `STATICFILES_DIRS` or run `collectstatic`:

```bash
python manage.py collectstatic
```

## Permissions

The dashboard respects Django admin permissions:
- Requires staff user authentication
- Uses the same queryset as the model's changelist view

## Django REST Framework Integration

The dashboard API uses DRF serializers when `djangorestframework` is installed.

### Installation

```bash
pip install django-easypay[drf]
# or
pip install djangorestframework
```

### Benefits

When DRF is installed:
- API responses are validated through `DashboardStatsSerializer`
- Consistent data structure guaranteed
- Better error handling with DRF's validation

### Standalone API View

For use outside of Django Admin:

```python
from easypay.dashboard.api import create_dashboard_api_view, DashboardAPIView
from myapp.models import Payment

# Factory function (works with or without DRF)
api_view = create_dashboard_api_view(lambda: Payment.objects.all())

# Or extend DashboardAPIView (requires DRF)
class MyDashboardAPI(DashboardAPIView):
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)
```

### Serializers

Available serializers in `easypay.dashboard.serializers`:

| Serializer | Description |
|------------|-------------|
| `DashboardStatsSerializer` | Complete dashboard statistics |
| `SummarySerializer` | Summary cards data |
| `ChartsSerializer` | Chart data (trend, status, method) |
| `ComparisonDataSerializer` | Period comparison data point |
| `SummaryCardSerializer` | Single summary card |
| `DailyTrendSerializer` | Daily revenue data point |
| `StatusBreakdownSerializer` | Status distribution item |
| `MethodBreakdownSerializer` | Payment method item |
