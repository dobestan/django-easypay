# Installation

## Requirements

- Python 3.11+
- Django 5.0+

## Install with uv (Recommended)

```bash
# From GitHub (private repo)
uv add git+https://github.com/dobestan/django-easypay.git

# With dev dependencies
uv add git+https://github.com/dobestan/django-easypay.git --extra dev
```

## Install with pip

```bash
pip install git+https://github.com/dobestan/django-easypay.git
```

## Configuration

### 1. Add to INSTALLED_APPS

```python
# settings.py
INSTALLED_APPS = [
    ...
    'easypay',
]
```

### 2. Configure EasyPay Settings

```python
# settings.py (or settings.toml for dynaconf)

# Test environment
EASYPAY_MALL_ID = "T0021792"
EASYPAY_API_URL = "https://testpgapi.easypay.co.kr"

# Production environment
EASYPAY_MALL_ID = "YOUR_MALL_ID"
EASYPAY_API_URL = "https://pgapi.easypay.co.kr"
```

### 3. Create Your Payment Model

```python
# apps/payments/models.py
from easypay.models import AbstractPayment

class Payment(AbstractPayment):
    """Your project's payment model."""
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE)

    class Meta:
        db_table = 'payments_payment'
```

### 4. Run Migrations

```bash
python manage.py makemigrations payments
python manage.py migrate
```

## Next Steps

- [Models](models.md) - Learn about AbstractPayment fields and methods
- [Signals](signals.md) - Handle payment events
- [Admin](admin.md) - Configure admin interface
- [Sandbox](sandbox.md) - Test payments locally
