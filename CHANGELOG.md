# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2024-12-29

### Changed
- Python 3.14 / Django 6.0 지원

## [1.0.0] - 2024-12-28

**Initial Release** - EasyPay (KICC) PG 결제 통합 Django 패키지

### Added

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
