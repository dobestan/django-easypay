# Admin Integration

django-easypay provides `PaymentAdminMixin` for easy Django admin integration.

## Basic Usage

```python
# apps/payments/admin.py
from django.contrib import admin
from easypay.admin import PaymentAdminMixin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(PaymentAdminMixin, admin.ModelAdmin):
    list_display = [
        'id',
        'user',
        'product',
    ] + PaymentAdminMixin.payment_list_display

    search_fields = [
        'user__email',
        'product__name',
    ] + PaymentAdminMixin.payment_search_fields

    list_filter = [
        'product',
    ] + PaymentAdminMixin.payment_list_filter
```

## Mixin Fields

### list_display Fields

| Field | Description |
|-------|-------------|
| `status_badge` | Colored status badge (green/yellow/red) |
| `amount_display` | Formatted amount with comma separator |
| `pay_method_display` | Payment method name |
| `created_at` | Creation timestamp |
| `paid_at` | Payment timestamp |
| `receipt_link` | Receipt view link (list) |

### search_fields

- `pg_tid`
- `auth_id`
- `card_no`

### list_filter

- `status`
- `pay_method`
- `card_name`
- `paid_at`
- `created_at`

## Detail Page Features

### Readonly Fields

```python
PaymentAdminMixin.payment_readonly_fields = [
    'pg_tid',
    'auth_id',
    'status',
    'card_no',
    'paid_at',
    'client_ip',
    'client_user_agent',
    'receipt_link_detail',
    'pg_status_info',
]
```

### Receipt Link

Provides a button to view the card receipt on EasyPay's site:

```python
def receipt_link_detail(self, obj):
    # Returns HTML button linking to receipt page
```

### PG Status Info

Shows real-time transaction status from EasyPay:

```python
def pg_status_info(self, obj):
    # Queries EasyPay API and displays current status
```

## Admin Actions

### Cancel Selected Payments

Bulk cancel completed payments:

```python
@admin.action(description="선택한 결제 취소")
def cancel_selected_payments(self, request, queryset):
    # Calls EasyPay cancel API for each payment
```

### Refresh Transaction Status

Sync local status with EasyPay:

```python
@admin.action(description="PG 상태 동기화")
def refresh_transaction_status(self, request, queryset):
    # Fetches current status from EasyPay
```

### Export to CSV

Download payment records:

```python
@admin.action(description="CSV 다운로드")
def export_to_csv(self, request, queryset):
    # Returns CSV file with payment data
```

## Customization

### Override Display Methods

```python
@admin.register(Payment)
class PaymentAdmin(PaymentAdminMixin, admin.ModelAdmin):
    def status_badge(self, obj):
        # Your custom status display
        badge = super().status_badge(obj)
        if obj.is_refunded:
            return format_html('<span style="color: purple;">환불</span>')
        return badge
```

### Add Custom Actions

```python
@admin.register(Payment)
class PaymentAdmin(PaymentAdminMixin, admin.ModelAdmin):
    actions = PaymentAdminMixin.payment_actions + ['send_receipt_email']

    @admin.action(description="영수증 이메일 발송")
    def send_receipt_email(self, request, queryset):
        for payment in queryset.filter(status='completed'):
            send_receipt_email.delay(payment.pk)
        self.message_user(request, f"{queryset.count()}건 발송 시작")
```

## Complete Example

```python
from django.contrib import admin
from django.utils.html import format_html
from easypay.admin import PaymentAdminMixin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(PaymentAdminMixin, admin.ModelAdmin):
    list_display = [
        'id',
        'user_link',
        'product',
        'status_badge',
        'amount_display',
        'card_name',
        'created_at',
        'receipt_link',
    ]

    list_filter = [
        'status',
        'pay_method',
        'card_name',
        ('created_at', admin.DateFieldListFilter),
        ('paid_at', admin.DateFieldListFilter),
    ]

    search_fields = [
        'user__email',
        'user__username',
        'product__name',
        'pg_tid',
        'auth_id',
    ]

    readonly_fields = PaymentAdminMixin.payment_readonly_fields + [
        'user',
        'product',
        'created_at',
    ]

    fieldsets = (
        ('기본 정보', {
            'fields': ('user', 'product', 'amount', 'status')
        }),
        ('결제 정보', {
            'fields': ('pg_tid', 'auth_id', 'pay_method', 'card_name', 'card_no')
        }),
        ('시간', {
            'fields': ('created_at', 'paid_at')
        }),
        ('클라이언트', {
            'fields': ('client_ip', 'client_user_agent'),
            'classes': ('collapse',)
        }),
        ('PG 연동', {
            'fields': ('receipt_link_detail', 'pg_status_info'),
            'classes': ('collapse',)
        }),
    )

    def user_link(self, obj):
        url = reverse('admin:auth_user_change', args=[obj.user.pk])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_link.short_description = '사용자'
```
