# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Payment Dashboard**: 결제 분석 대시보드 (`PaymentDashboardMixin`)
  - 요약 카드: 총 매출, 결제 건수, 평균 결제금액, 환불 건수
  - 일별 매출 추이 라인 차트 (Chart.js)
  - 상태별 분포 도넛 차트
  - 결제수단별 매출 바 차트
  - **기간 비교 차트**: 현재 vs 이전 기간 side-by-side 바 차트
  - 날짜 필터: 이번달(기본값), 오늘, 7일, 30일, 90일, 직접선택
  - **캘린더 날짜 선택기**: 월요일 시작, 주말 색상 구분 (토=파랑, 일=빨강)
  - **CSV 내보내기**: 선택 기간 결제 데이터 다운로드
  - JSON API 엔드포인트 (AJAX 업데이트용)
  - 반응형 디자인 (모바일/태블릿 대응)
  - 이전 기간 대비 변화율 표시
  - 주말 매출 시각적 구분 (차트에서 토/일 색상 다르게 표시)

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
