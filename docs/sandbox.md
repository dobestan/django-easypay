# Sandbox

The sandbox module provides a testing interface for EasyPay payments during development.

## Overview

- Works only in `DEBUG=True` mode
- Uses test MID (`T0021792`)
- Provides a simple web UI for testing payments
- Includes a concrete `SandboxPayment` model

## Setup

### 1. Add to INSTALLED_APPS

```python
# settings.py
INSTALLED_APPS = [
    ...
    'easypay',
    'easypay.sandbox',  # Add sandbox app
]
```

### 2. Include URLs (Development Only)

```python
# urls.py
from django.conf import settings
from django.urls import include, path

urlpatterns = [
    ...
]

if settings.DEBUG:
    urlpatterns += [
        path('easypay/sandbox/', include('easypay.sandbox.urls')),
    ]
```

### 3. Run Migrations

```bash
python manage.py migrate easypay_sandbox
```

## Usage

### Access the Sandbox

Visit `http://localhost:8000/easypay/sandbox/` in your browser.

### Test a Payment

1. Enter an amount (default: 1,000 KRW)
2. Enter a product name (optional)
3. Click "결제하기"
4. Complete payment on EasyPay test page
5. View result on callback page

## Test Cards

Any valid card works in the test environment. No actual charges are made.

| Card Type | Test |
|-----------|------|
| Credit Card | Any valid number |
| Expiry | Any future date |
| CVV | Any 3 digits |

## URLs

| URL | Name | Description |
|-----|------|-------------|
| `/easypay/sandbox/` | `easypay_sandbox:index` | Payment form |
| `/easypay/sandbox/pay/` | `easypay_sandbox:pay` | Start payment |
| `/easypay/sandbox/callback/` | `easypay_sandbox:callback` | Handle callback |

## SandboxPayment Model

The sandbox includes a concrete payment model for testing:

```python
from easypay.sandbox.models import SandboxPayment

# Create a test payment
payment = SandboxPayment.objects.create(
    amount=10000,
    goods_name="테스트 상품",
)

# Or use the factory method
payment = SandboxPayment.create_test_payment(
    amount=5000,
    goods_name="팩토리 상품",
)
payment.save()
```

### Factory Method

```python
SandboxPayment.create_test_payment(
    amount=10000,          # Required
    goods_name="상품명",    # Optional, default: "테스트 상품"
    client_ip="127.0.0.1", # Optional
)
```

## Security

The sandbox is protected by the `debug_required` decorator:

```python
from easypay.sandbox.views import debug_required

@debug_required
def my_test_view(request):
    # Only accessible when DEBUG=True
    ...
```

When `DEBUG=False`, all sandbox views return 403 Forbidden.

## Testing

Run sandbox tests:

```bash
# Run all sandbox tests
pytest tests/test_sandbox.py -v

# Run specific test class
pytest tests/test_sandbox.py::TestSandboxPaymentModel -v
```

## Customization

### Custom Test Page Template

Override `easypay/sandbox.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1>Custom Payment Test</h1>
<form method="post" action="{% url 'easypay_sandbox:pay' %}">
    {% csrf_token %}
    <input type="number" name="amount" value="1000">
    <button type="submit">Pay</button>
</form>
{% endblock %}
```

### Integration with Your Models

For production, use your own model inheriting from `AbstractPayment`:

```python
# apps/payments/models.py
from easypay.models import AbstractPayment

class Payment(AbstractPayment):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE)
```

The sandbox is just for quick testing without setting up your full payment flow.
