# Models

## AbstractPayment

The base abstract model for payment records. Inherit from this to create your project's payment model.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `pg_tid` | CharField(100) | EasyPay transaction ID (pgTid) |
| `auth_id` | CharField(100) | Authorization ID from callback |
| `amount` | DecimalField | Payment amount in KRW |
| `status` | CharField(20) | Payment status (see PaymentStatus) |
| `pay_method` | CharField(20) | Payment method code |
| `card_name` | CharField(50) | Card issuer name |
| `card_no` | CharField(20) | Masked card number |
| `client_ip` | GenericIPAddressField | Client IP address |
| `client_user_agent` | CharField(500) | Browser user agent |
| `created_at` | DateTimeField | Record creation time |
| `paid_at` | DateTimeField | Payment completion time |

### PaymentStatus

```python
from easypay.models import PaymentStatus

PaymentStatus.PENDING    # '결제대기'
PaymentStatus.COMPLETED  # '결제완료'
PaymentStatus.FAILED     # '결제실패'
PaymentStatus.CANCELLED  # '취소'
PaymentStatus.REFUNDED   # '환불'
```

### Properties

```python
payment.is_paid  # True if status == COMPLETED
```

### Methods

```python
# Mark payment as completed
payment.mark_as_paid(pg_tid="EASYPAY_TID_123", auth_id="AUTH456")

# Mark payment as failed
payment.mark_as_failed()
```

## Usage Example

```python
from django.db import models
from easypay.models import AbstractPayment

class Payment(AbstractPayment):
    """Project-specific payment model."""
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='payments'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE
    )

    # Add your custom fields
    order_number = models.CharField(max_length=50, unique=True)
    memo = models.TextField(blank=True)

    class Meta:
        db_table = 'payments_payment'
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment #{self.pk} - {self.amount:,}원"
```

## Custom Status Display

The model provides a human-readable `__str__` method:

```python
payment = Payment.objects.create(amount=29900)
print(payment)  # "29,900원 - 결제대기"

payment.mark_as_paid(pg_tid="TID123")
print(payment)  # "29,900원 - 결제완료"
```

## Indexes

AbstractPayment automatically creates database indexes on:
- `pg_tid`
- `auth_id`
- `status`
- `created_at`
- `paid_at`

These optimize common query patterns like filtering by status or date range.
