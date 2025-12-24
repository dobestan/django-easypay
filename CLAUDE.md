# Django EasyPay 모듈화 계획

## 결정 사항 (2024-12-24 업데이트)

| 항목 | 결정 |
|------|------|
| **호스팅** | GitHub Private (`dobestan/django-easypay`) |
| **설치 방식** | `uv add git+https://github.com/dobestan/django-easypay.git` |
| **모델명** | `Payment`로 통일 (sajudoctor Order → Payment 변경) |
| **명명 규칙** | EasyPay 공식 API 명칭 기반 explicit 네이밍 (약어 금지) |
| **적용 대상** | zipscan, realmbti, sajudoctor (irondoctor 미반영) |
| **데이터** | 테스트 환경이라 손실 허용 |

---

## Naming Conventions (명명 규칙)

### 원칙
1. **Explicit over Implicit**: 약어(abbreviation) 사용 금지
2. **EasyPay API 우선**: EasyPay 공식 API 필드명을 snake_case로 변환하여 사용
3. **일관성**: 모든 프로젝트에서 동일한 필드명 사용

### 필드 매핑 (EasyPay API → Django)

| EasyPay API (camelCase) | Django 필드 (snake_case) | 설명 |
|-------------------------|--------------------------|------|
| `authorizationId` | `authorization_id` | 결제 인증 ID |
| `payMethodTypeCode` | `pay_method_type_code` | 결제수단 코드 (11=카드, 21=계좌이체) |
| `deviceTypeCode` | `device_type_code` | 디바이스 타입 (PC, MOBILE) |
| `cancelTypeCode` | `cancel_type_code` | 취소 유형 (40=전체, 41=부분) |
| `pgTid` | `pg_tid` | PG 거래번호 |
| `shopOrderNo` | `order_id` | 주문번호 |

### 함수명 매핑

| 이전 함수명 | 현재 함수명 | 비고 |
|-------------|-------------|------|
| `get_device_type()` | `get_device_type_code()` | User-Agent 기반 PC/MOBILE 반환 |

### Signal 데이터 키

| Signal | 데이터 키 |
|--------|----------|
| `payment_approved` | `authorization_id`, `pay_method_type_code`, `card_name`, `card_no` |
| `payment_cancelled` | `cancel_type_code`, `cancel_amount` |

---

## 1. 현황 분석

### 1.1 공통 구성요소 (패키지화 대상)

| 구성요소 | 코드 위치 | 비고 |
|---------|----------|------|
| **EasyPayClient** | `*/easypay.py` | 3개 프로젝트 거의 동일 |
| **EasyPayError** | `*/easypay.py` | 동일한 예외 클래스 |
| **PG 필드들** | 각 모델 | pg_tid, authorization_id, amount, paid_at 등 |
| **Admin Mixin** | `*/admin.py` | 색상 배지, readonly 필드, 검색 |
| **IP 추출** | `*/utils.py` | `get_client_ip()` CloudFlare 대응 |
| **Device 감지** | `*/easypay.py` | User-Agent 기반 PC/MOBILE 구분 |

### 1.2 프로젝트별 변경 사항

| 항목 | sajudoctor | realmbti | zipscan |
|------|------------|----------|---------|
| 모델명 변경 | `Order` → `Payment` | 유지 | 유지 |
| 필드 변경 | - | - | 기존 `authorization_id` 유지 (패키지와 동일) |
| 연결 모델 | Product, SajuInfo | User, TestResult | Inquiry (1:1) |
| 후처리 | Report 생성, SMS | is_paid 플래그 | CODEF API 호출 |

---

## 2. 패키지 설계

### 2.1 패키지 구조

```
django-easypay/
├── pyproject.toml
├── README.md
├── easypay/
│   ├── __init__.py
│   ├── models.py          # AbstractPayment (추상 모델)
│   ├── client.py          # EasyPayClient
│   ├── exceptions.py      # EasyPayError
│   ├── views.py           # PaymentStartMixin, PaymentCallbackMixin
│   ├── admin.py           # PaymentAdminMixin
│   ├── settings.py        # EASYPAY_MALL_ID, EASYPAY_API_URL 기본값
│   ├── utils.py           # get_client_ip, get_device_type
│   └── apps.py            # Django AppConfig
```

### 2.2 Abstract Model 설계

```python
# easypay/models.py
from django.db import models

class PaymentStatus(models.TextChoices):
    PENDING = 'pending', '결제대기'
    COMPLETED = 'completed', '결제완료'
    FAILED = 'failed', '결제실패'
    CANCELLED = 'cancelled', '취소'
    REFUNDED = 'refunded', '환불'


class AbstractPayment(models.Model):
    """
    EasyPay 결제 정보를 저장하는 추상 모델.
    각 프로젝트에서 상속받아 사용.
    """
    # PG 트랜잭션 정보
    pg_tid = models.CharField('PG 거래번호', max_length=100, blank=True)
    authorization_id = models.CharField('인증번호', max_length=100, blank=True)

    # 결제 금액
    amount = models.DecimalField('결제금액', max_digits=10, decimal_places=0)

    # 결제 상태
    status = models.CharField(
        '상태',
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING
    )

    # 카드 정보 (마스킹됨)
    pay_method_type_code = models.CharField('결제수단', max_length=20, blank=True)
    card_name = models.CharField('카드사', max_length=50, blank=True)
    card_no = models.CharField('카드번호', max_length=20, blank=True)

    # 클라이언트 추적
    client_ip = models.GenericIPAddressField('클라이언트 IP', null=True, blank=True)
    client_user_agent = models.CharField('User Agent', max_length=500, blank=True)

    # 타임스탬프
    created_at = models.DateTimeField('생성일시', auto_now_add=True)
    paid_at = models.DateTimeField('결제일시', null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def is_paid(self) -> bool:
        return self.status == PaymentStatus.COMPLETED

    def mark_as_paid(self) -> None:
        from django.utils import timezone
        self.status = PaymentStatus.COMPLETED
        self.paid_at = timezone.now()
        self.save(update_fields=['status', 'paid_at'])

    def mark_as_failed(self) -> None:
        self.status = PaymentStatus.FAILED
        self.save(update_fields=['status'])
```

### 2.3 Signal 기반 확장성

```python
# easypay/signals.py
from django.dispatch import Signal

# 결제 상태 변경 시그널
payment_registered = Signal()    # 결제 등록 완료 (EasyPay authPageUrl 받음)
payment_approved = Signal()      # 결제 승인 완료 (PG 승인)
payment_failed = Signal()        # 결제 실패
payment_cancelled = Signal()     # 결제 취소/환불

# 각 시그널은 sender=Payment 모델, payment=인스턴스, 추가 데이터 전달
```

**사용 예시 (프로젝트에서):**
```python
# apps/payments/signals.py
from easypay.signals import payment_approved, payment_failed

@receiver(payment_approved)
def send_telegram_notification(sender, payment, **kwargs):
    """결제 승인 시 관리자에게 텔레그램 알림"""
    telegram_bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"💰 결제 완료!\n금액: {payment.amount:,}원\n상품: {payment.product_name}"
    )

@receiver(payment_approved)
def send_admin_sms(sender, payment, **kwargs):
    """결제 승인 시 관리자에게 SMS 알림"""
    send_sms(ADMIN_PHONE, f"[{SITE_NAME}] 결제 완료: {payment.amount:,}원")

@receiver(payment_failed)
def log_payment_failure(sender, payment, error_code, error_message, **kwargs):
    """결제 실패 시 Sentry 로깅"""
    sentry_sdk.capture_message(
        f"Payment failed: {error_code}",
        extra={'payment_id': payment.id, 'error': error_message}
    )
```

**AppConfig에서 Signal 연결:**
```python
# apps/payments/apps.py
class PaymentsConfig(AppConfig):
    def ready(self):
        from . import signals  # Signal receivers 로드
```

### 2.4 EasyPayClient 전체 API (결제 전문가 관점)

```python
# easypay/client.py
class EasyPayClient:
    """
    EasyPay PG API 클라이언트 (모든 운영 필수 API 포함)
    """

    def register_payment(self, payment, return_url: str, device_type_code: str = "PC") -> dict:
        """결제 등록 - authPageUrl 반환"""
        # POST /api/ep9/trades/webpay

    def approve_payment(self, payment, authorization_id: str) -> dict:
        """결제 승인 - 콜백 후 최종 승인"""
        # POST /api/ep9/trades/approval

    def cancel_payment(self, payment, cancel_type_code: str = "40", cancel_amount: int = None) -> dict:
        """결제 취소/환불 (전체/부분)"""
        # POST /api/ep9/trades/cancel
        # cancel_type_code: 40(전체취소), 41(부분취소)

    def get_transaction_status(self, payment, transaction_date: str = None) -> dict:
        """거래 상태 조회 - 영수증 정보 포함"""
        # POST /api/ep9/trades/status

    def get_receipt_url(self, pg_tid: str) -> str:
        """카드 영수증 URL 생성"""
        # https://testpgweb.easypay.co.kr/receipt/card?pgTid={pg_tid}
```

### 2.5 PaymentAdminMixin 설계 (운영 필수 기능)

```python
# easypay/admin.py
class PaymentAdminMixin:
    """
    결제 관리자 Mixin - 운영에 필요한 모든 기능 제공
    """

    # === list_display 확장 ===
    payment_list_display = [
        'status_badge',           # 색상 배지
        'amount_display',         # 금액 (천단위 콤마)
        'pay_method_type_code',   # 결제수단
        'card_name',              # 카드사
        'created_at',
        'paid_at',
        'receipt_link',           # 🆕 영수증 보기 링크
    ]

    # === Admin Actions ===
    actions = [
        'cancel_selected_payments',     # 🆕 선택 결제 취소
        'refresh_transaction_status',   # 🆕 PG 상태 동기화
        'export_to_csv',                # 🆕 CSV 다운로드
    ]

    # === 상세 페이지 기능 ===
    readonly_fields = [
        'pg_tid', 'authorization_id', 'card_no', 'paid_at',
        'client_ip', 'client_user_agent',
        'receipt_link_detail',   # 🆕 영수증 보기 버튼
        'pg_status_info',        # 🆕 PG 실시간 상태
    ]

    # === 검색/필터 ===
    payment_search_fields = ['pg_tid', 'authorization_id', 'card_no']
    payment_list_filter = ['status', 'pay_method_type_code', 'card_name', 'paid_at']

    # === 통계 뷰 (changelist 상단) ===
    def changelist_view(self, request, extra_context=None):
        """결제 통계 대시보드 추가"""
        # 오늘/이번주/이번달 매출 집계
        # 상태별 건수
        # 결제수단별 비율
```

### 2.6 결제 통계 기능

```python
# easypay/admin.py (통계 메서드)

def get_payment_statistics(self, queryset):
    """결제 통계 데이터 생성"""
    from django.db.models import Sum, Count
    from django.db.models.functions import TruncDate

    return {
        # 기간별 집계
        'today': {
            'count': queryset.filter(paid_at__date=today).count(),
            'total': queryset.filter(paid_at__date=today).aggregate(Sum('amount'))['amount__sum'] or 0,
        },
        'this_week': {...},
        'this_month': {...},

        # 상태별 집계
        'by_status': queryset.values('status').annotate(count=Count('id')),

        # 결제수단별 집계
        'by_method': queryset.values('pay_method_type_code').annotate(
            count=Count('id'),
            total=Sum('amount')
        ),

        # 일별 추이 (최근 7일)
        'daily_trend': queryset.filter(paid_at__gte=week_ago) \
            .annotate(date=TruncDate('paid_at')) \
            .values('date').annotate(total=Sum('amount')),
    }
```

### 2.7 영수증 조회 기능

```python
# easypay/admin.py (영수증 메서드)

def receipt_link(self, obj):
    """영수증 보기 링크 (리스트용)"""
    if obj.pg_tid:
        url = f"https://pgweb.easypay.co.kr/receipt/card?pgTid={obj.pg_tid}"
        return format_html(
            '<a href="{}" target="_blank" class="button">🧾</a>',
            url
        )
    return '-'
receipt_link.short_description = '영수증'

def receipt_link_detail(self, obj):
    """영수증 보기 버튼 (상세용)"""
    if obj.pg_tid:
        url = f"https://pgweb.easypay.co.kr/receipt/card?pgTid={obj.pg_tid}"
        return format_html(
            '<a href="{}" target="_blank" class="button" style="padding: 10px 20px;">'
            '🧾 카드 영수증 보기</a>',
            url
        )
    return '결제 전'
receipt_link_detail.short_description = '영수증'

def pg_status_info(self, obj):
    """PG 실시간 상태 조회"""
    if obj.pg_tid:
        try:
            status = easypay_client.get_transaction_status(obj)
            return format_html(
                '<div style="background:#f5f5f5;padding:10px;border-radius:4px;">'
                '<strong>PG 상태:</strong> {}<br>'
                '<strong>승인일시:</strong> {}<br>'
                '<strong>취소여부:</strong> {}'
                '</div>',
                status.get('payStatusNm', '-'),
                status.get('approvalDt', '-'),
                '취소됨' if status.get('cancelYn') == 'Y' else '정상'
            )
        except Exception as e:
            return f'조회 실패: {e}'
    return '결제 전'
pg_status_info.short_description = 'PG 실시간 상태'
```

### 2.8 Admin Actions 상세

```python
# easypay/admin.py (Admin Actions)

@admin.action(description="선택한 결제 취소 (환불 처리)")
def cancel_selected_payments(self, request, queryset):
    """선택한 결제 건 일괄 취소"""
    from easypay.signals import payment_cancelled

    cancelled = 0
    errors = []

    for payment in queryset.filter(status=PaymentStatus.COMPLETED):
        if payment.pg_tid:
            try:
                result = easypay_client.cancel_payment(payment)
                if result.get('resCd') == '0000':
                    payment.status = PaymentStatus.CANCELLED
                    payment.save()
                    payment_cancelled.send(sender=payment.__class__, payment=payment)
                    cancelled += 1
                else:
                    errors.append(f"{payment.id}: {result.get('resMsg')}")
            except Exception as e:
                errors.append(f"{payment.id}: {str(e)}")

    self.message_user(request, f"{cancelled}건 취소 완료")
    if errors:
        self.message_user(request, f"실패: {', '.join(errors)}", level='ERROR')


@admin.action(description="PG 거래 상태 동기화")
def refresh_transaction_status(self, request, queryset):
    """PG에서 최신 상태 가져와 동기화"""
    updated = 0
    for payment in queryset.filter(pg_tid__isnull=False):
        try:
            status = easypay_client.get_transaction_status(payment)
            # PG 상태에 따라 로컬 상태 업데이트
            if status.get('cancelYn') == 'Y' and payment.status != PaymentStatus.CANCELLED:
                payment.status = PaymentStatus.CANCELLED
                payment.save()
                updated += 1
        except:
            pass
    self.message_user(request, f"{updated}건 상태 동기화 완료")


@admin.action(description="CSV 다운로드")
def export_to_csv(self, request, queryset):
    """선택한 결제 내역 CSV 다운로드"""
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="payments_{date.today()}.csv"'

    writer = csv.writer(response)
    writer.writerow(['ID', '상태', '금액', '결제수단', '카드사', '결제일시', 'PG거래번호'])

    for p in queryset:
        writer.writerow([
            p.id, p.get_status_display(), p.amount,
            p.pay_method_type_code, p.card_name, p.paid_at, p.pg_tid
        ])

    return response
```

### 2.9 View Mixin 설계

```python
# easypay/views.py
class PaymentStartMixin:
    """결제 시작 뷰 Mixin"""

    def get_payment_object(self):
        """Override: 결제 대상 객체 반환"""
        raise NotImplementedError

    def get_return_url(self, payment):
        """Override: EasyPay 콜백 URL 반환"""
        raise NotImplementedError

    def get_product_name(self, payment):
        """Override: 상품명 반환"""
        raise NotImplementedError


class PaymentCallbackMixin:
    """EasyPay 콜백 처리 Mixin"""

    def on_payment_success(self, payment, approval_data):
        """Override: 결제 성공 후처리"""
        raise NotImplementedError

    def on_payment_failure(self, payment, error_code, error_message):
        """Override: 결제 실패 처리"""
        pass
```

### 2.10 확장 포인트 정리

| 확장 방식 | 용도 | 예시 |
|----------|------|------|
| **Signal** | 결제 이벤트 후처리 | 텔레그램, SMS, Slack 알림 |
| **Mixin Override** | 결제 플로우 커스터마이징 | 리포트 생성, API 호출 |
| **Model 상속** | 추가 필드 정의 | 상품, 사용자 연결 |
| **Admin Mixin** | 관리자 화면 커스터마이징 | 추가 액션, 필터 |

### 2.11 Sandbox URL 기능 (개발/테스트용)

#### 목적
- 패키지 설치 후 즉시 결제 플로우 테스트 가능
- Django Debug Toolbar 스타일의 선택적 URL 포함
- 실제 프로젝트와 독립적인 테스트 환경 제공

#### URL 구조
```python
# 프로젝트 urls.py (선택적 포함)
if settings.DEBUG:
    urlpatterns += [
        path('easypay/sandbox/', include('easypay.sandbox.urls')),
    ]
```

#### 파일 구조
```
easypay/
├── sandbox/
│   ├── __init__.py
│   ├── urls.py              # URL 패턴 정의
│   ├── views.py             # SandboxView, CallbackView
│   └── templates/
│       └── easypay/
│           ├── sandbox.html   # 결제 테스트 폼
│           └── callback.html  # 결제 결과 페이지
```

#### 제공 기능 (최소한)
| 기능 | 설명 | 포함 |
|------|------|------|
| 결제 테스트 | 금액 입력 → 결제창 → 결과 | ✅ |
| 결제 취소 | Admin에서 처리 | ❌ (불필요) |
| 거래 조회 | Admin에서 처리 | ❌ (불필요) |

#### 보안
- `DEBUG=True`일 때만 접근 가능
- 프로덕션 환경에서 자동 비활성화
- 테스트 MID (`T0021792`) 사용

#### 템플릿 스타일
- 최소한의 HTML (CSS 프레임워크 없음)
- 인라인 CSS로 기본 스타일링
- 모바일 반응형 기본 지원

#### View 구현
```python
# easypay/sandbox/views.py
from django.views import View
from django.shortcuts import render
from django.http import HttpResponseForbidden
from django.conf import settings

class SandboxView(View):
    """결제 테스트 폼 페이지"""
    def get(self, request):
        if not settings.DEBUG:
            return HttpResponseForbidden("Sandbox is only available in DEBUG mode")
        return render(request, 'easypay/sandbox.html')

    def post(self, request):
        # EasyPayClient로 결제 등록 → authPageUrl로 리다이렉트
        pass

class CallbackView(View):
    """결제 콜백 처리 및 결과 표시"""
    def get(self, request):
        # authorizationId로 결제 승인 → 결과 표시
        pass
```

---

## 3. 마이그레이션 전략

### 3.1 핵심 원칙

**테스트 환경이므로 Clean Slate 접근 가능**

- 기존 테이블 삭제 후 새 테이블 생성 허용
- 모델명/테이블명 통일 가능 (`Payment`, `payments_payment`)
- 데이터 손실 허용

### 3.2 프로젝트별 마이그레이션

#### zipscan (가장 먼저)
```bash
# 1. 기존 테이블 삭제 (테스트 데이터 손실 OK)
python manage.py migrate inquiries zero

# 2. 필드명 변경된 모델로 교체 후
python manage.py makemigrations inquiries
python manage.py migrate inquiries
```

#### realmbti
```bash
# 1. 기존 테이블 삭제
python manage.py migrate payments zero

# 2. AbstractPayment 상속 모델로 교체 후
python manage.py makemigrations payments
python manage.py migrate payments
```

#### sajudoctor (가장 큰 변경)
```bash
# 1. Order → Payment 모델명 변경
# 2. orders 앱을 payments 앱으로 리네임 (또는 유지)
# 3. 기존 테이블 삭제 후 새로 생성

python manage.py migrate orders zero
# 앱 구조 변경 후
python manage.py makemigrations
python manage.py migrate
```

### 3.3 단계별 진행

#### Phase 1: 패키지 개발
1. GitHub Private 저장소 생성: `dobestan/django-easypay`
2. AbstractPayment, EasyPayClient, Mixin 개발
3. 로컬 테스트

#### Phase 2: zipscan 적용 (첫 번째)
1. AbstractPayment 상속으로 전환 (필드명 동일: `authorization_id`)
2. 서버 배포 및 검증

#### Phase 3: realmbti 적용
1. AbstractPayment 상속으로 전환
2. 서버 배포 및 검증

#### Phase 4: sajudoctor 적용 (가장 큰 변경)
1. Order → Payment 모델명 변경
2. 관련 코드 전체 수정 (views, templates, urls, admin)
3. 서버 배포 및 검증

---

## 4. 설치 및 사용

### 4.1 설치

```bash
# Git URL로 설치 (초기)
uv add git+https://github.com/dobestan/django-easypay.git

# 또는 PyPI (추후)
uv add django-easypay
```

### 4.2 설정

```python
# settings.py
INSTALLED_APPS = [
    ...
    'easypay',
]

# 또는 settings.toml (dynaconf)
EASYPAY_MALL_ID = "T0021792"  # 테스트 MID
EASYPAY_API_URL = "https://testpgapi.easypay.co.kr"
```

### 4.3 사용 예시

```python
# models.py
from easypay.models import AbstractPayment

class Order(AbstractPayment):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    class Meta:
        db_table = 'orders_order'


# views.py
from easypay.views import PaymentStartMixin, PaymentCallbackMixin
from easypay.client import easypay_client

class PaymentStartView(PaymentStartMixin, View):
    def get_payment_object(self):
        return get_object_or_404(Order, hash_id=self.kwargs['hash_id'])

    def get_return_url(self, order):
        return self.request.build_absolute_uri(
            reverse('orders:callback', args=[order.hash_id])
        )


# admin.py
from easypay.admin import PaymentAdminMixin

@admin.register(Order)
class OrderAdmin(PaymentAdminMixin, admin.ModelAdmin):
    list_display = ['hash_id', 'user', 'product'] + PaymentAdminMixin.payment_list_display
```

---

## 5. 작업 항목

### 5.1 Phase 1: 패키지 개발 (`django-easypay`)

**저장소 설정:**
- [ ] GitHub Private 저장소 생성: `dobestan/django-easypay`
- [ ] pyproject.toml 설정 (uv 호환, Python 3.11+)

**핵심 모듈:**
- [ ] `easypay/models.py` - AbstractPayment, PaymentStatus
- [ ] `easypay/client.py` - EasyPayClient
  - [ ] `register_payment()` - 결제 등록 (authPageUrl 반환)
  - [ ] `approve_payment()` - 결제 승인 (콜백 후 최종 승인)
  - [ ] `cancel_payment()` - 결제 취소/환불 (전체/부분)
  - [ ] `get_transaction_status()` - 거래 상태 조회 (🆕 운영 필수)
  - [ ] `get_receipt_url()` - 카드 영수증 URL 생성 (🆕 운영 필수)
- [ ] `easypay/exceptions.py` - EasyPayError
- [ ] `easypay/signals.py` - payment_registered, payment_approved, payment_failed, payment_cancelled
- [ ] `easypay/admin.py` - PaymentAdminMixin
  - [ ] `status_badge()` - 상태 색상 배지
  - [ ] `receipt_link()` - 영수증 보기 링크 (리스트용) (🆕)
  - [ ] `receipt_link_detail()` - 영수증 보기 버튼 (상세용) (🆕)
  - [ ] `pg_status_info()` - PG 실시간 상태 조회 (🆕)
  - [ ] `get_payment_statistics()` - 결제 통계 데이터 (🆕)
  - [ ] Admin Actions:
    - [ ] `cancel_selected_payments` - 선택 결제 일괄 취소 (🆕)
    - [ ] `refresh_transaction_status` - PG 상태 동기화 (🆕)
    - [ ] `export_to_csv` - CSV 다운로드 (🆕)
- [ ] `easypay/utils.py` - get_client_ip, get_device_type_code

**문서화 (docs/):**
- [ ] `README.md` - 설치, Quick Start
- [ ] `docs/installation.md` - 상세 설치 가이드, uv 사용법
- [ ] `docs/models.md` - AbstractPayment 상속, 필드 설명
- [ ] `docs/signals.md` - Signal 목록, 사용 예시 (텔레그램, SMS, Slack)
- [ ] `docs/admin.md` - PaymentAdminMixin 사용법
  - [ ] 영수증 조회 기능 설명 (🆕)
  - [ ] 결제 통계 대시보드 설명 (🆕)
  - [ ] Admin Actions 사용법 (🆕)
- [ ] `docs/upgrade.md` - 업데이트 방법 (`uv sync`, 버전 관리)

**선택 모듈 (추후):**
- [ ] `easypay/views.py` - PaymentStartMixin, PaymentCallbackMixin
- [ ] 테스트 코드 작성

### 5.2 Phase 2: zipscan 적용 (첫 번째)

**수정 파일:**
- [ ] `inquiries/models.py` - AbstractPayment 상속 (필드명 동일: `authorization_id`)
- [ ] `inquiries/easypay.py` → 패키지 import로 교체
- [ ] `inquiries/views.py` - client import 경로 변경
- [ ] `inquiries/admin.py` - PaymentAdminMixin 적용

**마이그레이션:**
- [ ] 기존 테이블 삭제: `python manage.py migrate inquiries zero`
- [ ] 새 마이그레이션 생성 및 적용
- [ ] 서버 배포: `ssh zipscan && git pull && migrate`

### 5.3 Phase 3: realmbti 적용

**수정 파일:**
- [ ] `apps/payments/models.py` - AbstractPayment 상속
- [ ] `apps/payments/easypay.py` → 패키지 import로 교체
- [ ] `apps/payments/views.py` - client import 경로 변경
- [ ] `apps/payments/admin.py` - PaymentAdminMixin 적용

**마이그레이션:**
- [ ] 기존 테이블 삭제: `python manage.py migrate payments zero`
- [ ] 새 마이그레이션 생성 및 적용
- [ ] 서버 배포

### 5.4 Phase 4: sajudoctor 적용 (가장 큰 변경)

**앱 구조 변경:**
- [ ] `apps/orders/` → `apps/payments/` 앱 리네임 (또는 유지하고 모델만 변경)
- [ ] `Order` → `Payment` 모델명 변경

**수정 파일 (모델명 변경 영향):**
- [ ] `apps/orders/models.py` - Order → Payment, AbstractPayment 상속
- [ ] `apps/orders/views.py` - Order → Payment 참조 변경
- [ ] `apps/orders/admin.py` - OrderAdmin → PaymentAdmin
- [ ] `apps/orders/urls.py` - 경로 유지 또는 변경
- [ ] `apps/orders/tasks.py` - 모델 참조 변경
- [ ] `apps/reports/` - Order FK → Payment FK
- [ ] `templates/orders/` - 템플릿 변수명 변경 (order → payment)
- [ ] `config/urls.py` - app 경로 확인

**마이그레이션:**
- [ ] 기존 테이블 삭제
- [ ] 새 마이그레이션 생성 및 적용
- [ ] 서버 배포

---

## 6. 위험 요소 및 대응

### 6.1 마이그레이션 위험

| 위험 | 확률 | 대응 |
|------|------|------|
| 필드 타입 불일치 | 낮음 | Abstract 모델 필드 타입을 기존과 동일하게 정의 |
| db_table 누락 | 중간 | 체크리스트로 확인 필수 |
| Foreign Key 깨짐 | 낮음 | FK는 상속 모델에서 정의 (Abstract에 포함 안함) |

### 6.2 버전 관리

- 패키지 버전: SemVer (1.0.0 시작)
- Breaking change 시 Major 버전 업
- 각 프로젝트에서 버전 고정: `django-easypay==1.0.0`

---

## 7. 결론

**마이그레이션 복잡도: 낮음 ~ 중간**

Abstract Model 패턴을 사용하면:
1. 기존 테이블 구조 변경 없음
2. 데이터 이전 불필요
3. `db_table` 명시로 기존 테이블명 유지
4. 점진적 전환 가능 (프로젝트별 독립 적용)

**스키마 변경 없음** - EasyPay 공식 API 명칭(`authorization_id`)을 그대로 사용하여 기존 프로젝트와 호환

**권장 진행 순서:**
1. 패키지 개발 및 테스트 ✅ (277 tests passed)
2. realmbti 적용 ✅
3. zipscan 적용 (pending)
4. sajudoctor 적용 (pending)
