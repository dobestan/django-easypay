# django-easypay

Django payment integration for EasyPay (KICC) PG.

EasyPay (KICC)는 한국의 주요 PG(Payment Gateway) 서비스입니다. 이 패키지는 Django 프로젝트에서 EasyPay 결제를 쉽게 연동할 수 있도록 추상 모델, API 클라이언트, Admin Mixin 등을 제공합니다.

## Features

- **AbstractPayment Model**: 결제 정보를 저장하는 추상 모델 (상속하여 사용)
- **EasyPayClient**: 결제 등록, 승인, 취소, 상태조회 API
- **PaymentAdminMixin**: 결제 관리를 위한 Admin Mixin (통계, CSV 내보내기, 일괄 취소)
- **Signals**: 결제 이벤트 시그널 (등록, 승인, 실패, 취소)
- **Sandbox**: 결제 플로우 테스트를 위한 샌드박스 모듈

## Installation

### Git (Private Repository)

```bash
# uv
uv add git+https://github.com/dobestan/django-easypay.git

# pip
pip install git+https://github.com/dobestan/django-easypay.git
```

### PyPI (추후 예정)

```bash
uv add django-easypay
```

## Quick Start

### 1. Settings 설정

```python
# settings.py
INSTALLED_APPS = [
    ...
    'easypay',
]

# EasyPay 설정 (선택 - 기본값: 테스트 MID)
EASYPAY_MALL_ID = "T0021792"  # 테스트 MID (기본값)
EASYPAY_API_URL = "https://testpgapi.easypay.co.kr"  # 테스트 URL (기본값)
```

### 2. Payment 모델 생성

```python
# apps/payments/models.py
from django.db import models
from easypay.models import AbstractPayment

class Payment(AbstractPayment):
    """프로젝트별 결제 모델"""

    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE)

    class Meta:
        db_table = 'payments_payment'
```

### 3. Migration 실행

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. 결제 뷰 구현

```python
# apps/payments/views.py
from django.shortcuts import redirect, get_object_or_404
from django.views import View
from easypay.client import EasyPayClient
from easypay.utils import get_client_ip, get_device_type, get_user_agent

class PaymentStartView(View):
    """결제 시작 뷰"""

    def post(self, request, payment_id):
        payment = get_object_or_404(Payment, pk=payment_id)

        # 클라이언트 정보 저장
        payment.client_ip = get_client_ip(request)
        payment.client_user_agent = get_user_agent(request)
        payment.save()

        # EasyPay 결제 등록
        client = EasyPayClient()
        result = client.register_payment(
            payment=payment,
            return_url=request.build_absolute_uri(f'/payments/{payment.pk}/callback/'),
            goods_name=payment.product.name,
            customer_name=payment.user.username,
            device_type=get_device_type(request),
        )

        # 결제 페이지로 리다이렉트
        return redirect(result['authPageUrl'])


class PaymentCallbackView(View):
    """EasyPay 콜백 뷰"""

    def get(self, request, payment_id):
        payment = get_object_or_404(Payment, pk=payment_id)
        auth_id = request.GET.get('authorizationId')

        if not auth_id:
            payment.mark_as_failed()
            return render(request, 'payments/failed.html')

        # 결제 승인
        client = EasyPayClient()
        result = client.approve_payment(payment=payment, auth_id=auth_id)

        # 결제 완료 처리
        payment.mark_as_paid(
            pg_tid=result.get('pgTid'),
            auth_id=auth_id,
            pay_method=result.get('paymentInfo', {}).get('payMethodTypeCode'),
            card_name=result.get('paymentInfo', {}).get('cardInfo', {}).get('cardName'),
            card_no=result.get('paymentInfo', {}).get('cardInfo', {}).get('cardNo'),
        )

        return render(request, 'payments/success.html', {'payment': payment})
```

### 5. Admin 설정

```python
# apps/payments/admin.py
from django.contrib import admin
from easypay.admin import PaymentAdminMixin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(PaymentAdminMixin, admin.ModelAdmin):
    list_display = ['id', 'user', 'product'] + PaymentAdminMixin.payment_list_display
    list_filter = ['status', 'pay_method', 'created_at', 'paid_at']
    search_fields = ['pg_tid', 'auth_id', 'user__username']
```

## Signal 연결

결제 이벤트에 따른 후처리 로직을 Signal로 연결할 수 있습니다.

```python
# apps/payments/signals.py
from django.dispatch import receiver
from easypay.signals import payment_approved, payment_failed

@receiver(payment_approved)
def send_payment_notification(sender, payment, approval_data, **kwargs):
    """결제 완료 시 알림 발송"""
    # SMS 발송
    send_sms(payment.user.phone, f"결제가 완료되었습니다. 금액: {payment.amount:,}원")

    # Slack 알림
    slack_notify(f"💰 결제 완료: {payment.amount:,}원 - {payment.user.username}")

@receiver(payment_failed)
def log_payment_failure(sender, payment, error_code, error_message, stage, **kwargs):
    """결제 실패 시 로깅"""
    import sentry_sdk
    sentry_sdk.capture_message(
        f"Payment failed: {error_code}",
        extra={'payment_id': payment.pk, 'error': error_message, 'stage': stage}
    )
```

```python
# apps/payments/apps.py
class PaymentsConfig(AppConfig):
    name = 'apps.payments'

    def ready(self):
        from . import signals  # Signal receivers 로드
```

## Sandbox (테스트 환경)

패키지 설치 후 바로 결제 플로우를 테스트할 수 있습니다.

### 설정

```python
# urls.py (개발 환경에서만)
from django.conf import settings

if settings.DEBUG:
    urlpatterns += [
        path('easypay/sandbox/', include('easypay.sandbox.urls')),
    ]
```

```python
# settings.py
INSTALLED_APPS = [
    ...
    'easypay',
    'easypay.sandbox',  # Sandbox 사용 시 추가
]
```

### 마이그레이션

```bash
python manage.py migrate easypay_sandbox
```

### 접속

개발 서버 실행 후 `http://localhost:8000/easypay/sandbox/` 접속

> ⚠️ Sandbox는 `DEBUG=True` 환경에서만 접근 가능합니다.

## API Reference

### AbstractPayment Fields

| 필드 | 타입 | 설명 |
|------|------|------|
| `pg_tid` | CharField(100) | PG 거래번호 |
| `auth_id` | CharField(100) | 인증번호 |
| `amount` | DecimalField | 결제금액 (원) |
| `status` | CharField(20) | 결제상태 |
| `pay_method` | CharField(20) | 결제수단 코드 |
| `card_name` | CharField(50) | 카드사명 |
| `card_no` | CharField(20) | 카드번호 (마스킹) |
| `client_ip` | GenericIPAddressField | 클라이언트 IP |
| `client_user_agent` | CharField(500) | User Agent |
| `created_at` | DateTimeField | 생성일시 |
| `paid_at` | DateTimeField | 결제일시 |

### AbstractPayment Methods

| 메서드 | 설명 |
|--------|------|
| `is_paid` | 결제 완료 여부 (property) |
| `is_pending` | 결제 대기 여부 (property) |
| `can_cancel` | 취소 가능 여부 (property) |
| `mark_as_paid()` | 결제 완료 처리 |
| `mark_as_failed()` | 결제 실패 처리 |
| `mark_as_cancelled()` | 취소 처리 |
| `get_receipt_url()` | 영수증 URL 반환 |

### PaymentStatus Choices

| 값 | 라벨 |
|-----|------|
| `pending` | 결제대기 |
| `completed` | 결제완료 |
| `failed` | 결제실패 |
| `cancelled` | 취소 |
| `refunded` | 환불 |

### EasyPayClient Methods

| 메서드 | 설명 |
|--------|------|
| `register_payment()` | 결제 등록 → authPageUrl 반환 |
| `approve_payment()` | 결제 승인 (콜백 후) |
| `cancel_payment()` | 결제 취소/환불 |
| `get_transaction_status()` | 거래 상태 조회 |
| `get_receipt_url()` | 영수증 URL 생성 |

### Signals

| 시그널 | 발생 시점 | 전달 데이터 |
|--------|----------|------------|
| `payment_registered` | 결제 등록 완료 | payment, auth_page_url |
| `payment_approved` | 결제 승인 완료 | payment, approval_data |
| `payment_failed` | 결제 실패 | payment, error_code, error_message, stage |
| `payment_cancelled` | 결제 취소 완료 | payment, cancel_type, cancel_amount, cancel_data |

## Utility Functions

```python
from easypay.utils import (
    get_client_ip,      # 실제 클라이언트 IP 추출 (CloudFlare 대응)
    get_device_type,    # PC/MOBILE 구분
    get_user_agent,     # User-Agent 추출
    mask_card_number,   # 카드번호 마스킹
    format_amount,      # 금액 포맷 (29,900원)
)
```

## Security

이 패키지는 PCI-DSS 준수를 고려하여 설계되었습니다.

### 보안 기능

- **카드번호 마스킹**: `mask_card_number()` 함수로 카드번호 자동 마스킹
- **민감 데이터 보호**: `auth_id`는 로그 및 CSV 내보내기에서 제외
- **감사 로깅**: Admin 액션 (취소, 내보내기) 자동 로깅
- **금액 검증**: 승인 금액과 요청 금액 불일치 시 ERROR 로그
- **Idempotency**: `select_for_update()`로 중복 결제 승인 방지

### 로깅 가이드

```python
# ✅ 안전한 로깅 (권장)
logger.info("Payment approved", extra={
    "payment_id": payment.pk,
    "order_id": payment.order_id,
    "amount": int(payment.amount),
    "pg_tid": payment.pg_tid,
})

# ❌ 위험한 로깅 (금지)
logger.info(f"Auth ID: {payment.auth_id}")  # 민감 정보
logger.info(f"Full response: {api_response}")  # 전체 응답
```

자세한 내용은 [보안 가이드](docs/security.md)를 참조하세요.

## Admin Features

`PaymentAdminMixin`은 다음 기능을 제공합니다:

| 기능 | 설명 |
|------|------|
| **상태 배지** | 상태별 색상 배지 (pending=노랑, completed=초록, failed=빨강) |
| **영수증 링크** | PG 영수증 페이지 바로가기 |
| **PG 상태 조회** | 실시간 PG 거래 상태 확인 |
| **결제 통계** | 일별/주별/월별 매출 통계 대시보드 |
| **일괄 취소** | 선택한 결제 건 일괄 취소 |
| **CSV 내보내기** | 결제 내역 CSV 다운로드 (카드번호 마스킹) |

## Requirements

- Python >= 3.12
- Django >= 5.0 (Django 6.0 지원)
- requests >= 2.28

## Changelog

### v1.0.0 (2024-12-28)

**Initial Release** - EasyPay (KICC) PG 결제 통합 Django 패키지

#### Features
- **AbstractPayment Model**: 결제 정보를 저장하는 추상 모델
  - `PaymentStatus` choices (pending, completed, failed, cancelled, refunded)
  - `mark_as_paid()`, `mark_as_failed()`, `mark_as_cancelled()` 메서드
  - `is_paid`, `is_pending`, `can_cancel` properties
  - `get_receipt_url()` 영수증 URL 생성

- **EasyPayClient**: EasyPay API 클라이언트
  - `register_payment()` - 결제 등록 (authPageUrl 반환)
  - `approve_payment()` - 결제 승인
  - `cancel_payment()` - 전체/부분 취소
  - `get_transaction_status()` - 거래 상태 조회
  - TypedDict 기반 타입 힌트 지원

- **PaymentAdminMixin**: Django Admin 통합
  - 상태별 색상 배지
  - 영수증 링크 및 PG 상태 조회
  - 결제 통계 대시보드 (일별/주별/월별)
  - 일괄 취소 및 CSV 내보내기 액션

- **Signals**: 결제 이벤트 시그널
  - `payment_registered` - 결제 등록 완료
  - `payment_approved` - 결제 승인 완료
  - `payment_failed` - 결제 실패
  - `payment_cancelled` - 결제 취소

- **Sandbox**: 결제 플로우 테스트 환경
  - DEBUG 모드에서만 접근 가능
  - 실제 EasyPay 테스트 서버 연동

- **Security**: PCI-DSS 준수 고려
  - 카드번호 마스킹
  - 민감 데이터 로깅 보호
  - 감사 로깅

- **Utilities**: 유틸리티 함수
  - `get_client_ip()` - CloudFlare 대응 IP 추출
  - `get_device_type_code()` - PC/MOBILE 구분
  - `mask_card_number()` - 카드번호 마스킹

#### Technical
- Python 3.12+ 지원
- Django 5.0, 5.1, 6.0 지원
- mypy 타입 체크 통과
- 277 테스트 케이스

## Documentation

- [설치 가이드](docs/installation.md)
- [모델 상속](docs/models.md)
- [시그널 사용법](docs/signals.md)
- [Admin Mixin](docs/admin.md)
- [보안 가이드](docs/security.md)

## License

MIT License

## Links

- [EasyPay Developer Center](https://developer.easypay.co.kr)
- [결제 등록 API](https://developer.easypay.co.kr/integrated-api/payRegistration)
- [결제수단 코드](https://developer.easypay.co.kr/reference-codes/paymentCode)
