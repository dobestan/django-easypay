"""
Tests for EasyPay utility functions.

Tests cover:
- get_client_ip: CloudFlare, Nginx, X-Forwarded-For, direct connection
- get_device_type_code: Mobile vs PC detection from User-Agent
- get_user_agent: User-Agent extraction and truncation
- mask_card_number: Card number masking for display
- format_amount: Korean Won formatting
- normalize_phone: Phone number normalization
"""

import pytest

from easypay.utils import (
    format_amount,
    get_client_ip,
    get_device_type_code,
    get_user_agent,
    mask_card_number,
    normalize_phone,
)

# ============================================================
# get_client_ip Tests
# ============================================================


class TestGetClientIP:
    """Tests for IP address extraction from various proxy scenarios."""

    def test_cloudflare_ip_takes_priority(self, mock_cloudflare_request):
        """CloudFlare's CF-Connecting-IP header should be prioritized."""
        ip = get_client_ip(mock_cloudflare_request)
        assert ip == "203.0.113.50"

    def test_nginx_x_real_ip(self, request_factory):
        """X-Real-IP header should be used when CF header is absent."""
        request = request_factory.get("/")
        request.META["HTTP_X_REAL_IP"] = "10.0.0.100"
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        ip = get_client_ip(request)
        assert ip == "10.0.0.100"

    def test_x_forwarded_for_first_ip(self, request_factory):
        """First IP in X-Forwarded-For chain should be used."""
        request = request_factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "192.168.1.1, 10.0.0.1, 172.16.0.1"
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        ip = get_client_ip(request)
        assert ip == "192.168.1.1"

    def test_x_forwarded_for_with_spaces(self, request_factory):
        """Whitespace should be trimmed from X-Forwarded-For IPs."""
        request = request_factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "  192.168.1.1  ,  10.0.0.1  "

        ip = get_client_ip(request)
        assert ip == "192.168.1.1"

    def test_remote_addr_fallback(self, request_factory):
        """REMOTE_ADDR should be used as last resort."""
        request = request_factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        ip = get_client_ip(request)
        assert ip == "127.0.0.1"

    def test_empty_when_no_ip(self, request_factory):
        """Empty string when no IP information is available."""
        request = request_factory.get("/")
        # Clear any default REMOTE_ADDR
        if "REMOTE_ADDR" in request.META:
            del request.META["REMOTE_ADDR"]

        ip = get_client_ip(request)
        assert ip == ""

    def test_cf_ip_with_whitespace(self, request_factory):
        """CloudFlare IP with whitespace should be trimmed."""
        request = request_factory.get("/")
        request.META["HTTP_CF_CONNECTING_IP"] = "  203.0.113.50  "

        ip = get_client_ip(request)
        assert ip == "203.0.113.50"

    def test_ipv6_address(self, request_factory):
        """IPv6 addresses should be handled correctly."""
        request = request_factory.get("/")
        request.META["HTTP_CF_CONNECTING_IP"] = "2001:db8::1"

        ip = get_client_ip(request)
        assert ip == "2001:db8::1"


# ============================================================
# get_device_type_code Tests
# ============================================================


class TestGetDeviceTypeCode:
    """Tests for mobile vs PC device detection (EasyPay deviceTypeCode)."""

    # Mobile User-Agents
    @pytest.mark.parametrize(
        "user_agent",
        [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
            "Mozilla/5.0 (Linux; Android 11; SM-G991B)",
            "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X)",
            "Mozilla/5.0 (Linux; Android 10; Mobile)",
            "Mozilla/5.0 (compatible; MSIE 10.0; Windows Phone 8.0)",
            "Opera Mini/8.0.1807/37.7549",
            "Mozilla/5.0 (webOS/2.0; U; en-US)",
            "BlackBerry9700/5.0.0.862 Profile/MIDP-2.1",
        ],
    )
    def test_mobile_user_agents(self, request_factory, user_agent):
        """Various mobile User-Agents should return MOBILE."""
        request = request_factory.get("/")
        request.META["HTTP_USER_AGENT"] = user_agent

        device_type_code = get_device_type_code(request)
        assert device_type_code == "MOBILE"

    # PC User-Agents
    @pytest.mark.parametrize(
        "user_agent",
        [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0)",
        ],
    )
    def test_pc_user_agents(self, request_factory, user_agent):
        """Desktop User-Agents should return PC."""
        request = request_factory.get("/")
        request.META["HTTP_USER_AGENT"] = user_agent

        device_type_code = get_device_type_code(request)
        assert device_type_code == "PC"

    def test_empty_user_agent_returns_pc(self, request_factory):
        """Empty or missing User-Agent should default to PC."""
        request = request_factory.get("/")
        request.META["HTTP_USER_AGENT"] = ""

        device_type_code = get_device_type_code(request)
        assert device_type_code == "PC"

    def test_missing_user_agent_returns_pc(self, request_factory):
        """Missing User-Agent header should default to PC."""
        request = request_factory.get("/")
        if "HTTP_USER_AGENT" in request.META:
            del request.META["HTTP_USER_AGENT"]

        device_type_code = get_device_type_code(request)
        assert device_type_code == "PC"

    def test_case_insensitive_detection(self, request_factory):
        """Mobile detection should be case-insensitive."""
        request = request_factory.get("/")
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0 (IPHONE; CPU iPhone OS)"

        device_type_code = get_device_type_code(request)
        assert device_type_code == "MOBILE"

    def test_fixture_mobile_request(self, mock_mobile_request):
        """Test with mock_mobile_request fixture."""
        device_type_code = get_device_type_code(mock_mobile_request)
        assert device_type_code == "MOBILE"

    def test_fixture_pc_request(self, mock_request):
        """Test with mock_request fixture (PC)."""
        device_type_code = get_device_type_code(mock_request)
        assert device_type_code == "PC"


# ============================================================
# get_user_agent Tests
# ============================================================


class TestGetUserAgent:
    """Tests for User-Agent extraction and truncation."""

    def test_extracts_user_agent(self, mock_request):
        """User-Agent header should be extracted correctly."""
        user_agent = get_user_agent(mock_request)
        assert "Mozilla/5.0" in user_agent
        assert "AppleWebKit/537.36" in user_agent

    def test_empty_when_missing(self, request_factory):
        """Empty string when User-Agent is missing."""
        request = request_factory.get("/")
        if "HTTP_USER_AGENT" in request.META:
            del request.META["HTTP_USER_AGENT"]

        user_agent = get_user_agent(request)
        assert user_agent == ""

    def test_truncation_at_500_chars(self, request_factory):
        """Long User-Agent should be truncated to 500 characters."""
        request = request_factory.get("/")
        long_ua = "A" * 600
        request.META["HTTP_USER_AGENT"] = long_ua

        user_agent = get_user_agent(request)
        assert len(user_agent) == 500
        assert user_agent == "A" * 500

    def test_exact_500_chars_not_truncated(self, request_factory):
        """User-Agent of exactly 500 chars should not be truncated."""
        request = request_factory.get("/")
        exact_ua = "B" * 500
        request.META["HTTP_USER_AGENT"] = exact_ua

        user_agent = get_user_agent(request)
        assert len(user_agent) == 500
        assert user_agent == exact_ua


# ============================================================
# mask_card_number Tests
# ============================================================


class TestMaskCardNumber:
    """Tests for card number masking."""

    def test_mask_16_digit_card(self):
        """Standard 16-digit card should be masked correctly."""
        masked = mask_card_number("1234567890123456")
        assert masked == "1234-****-****-3456"

    def test_mask_formatted_card(self):
        """Already formatted card should be masked correctly."""
        masked = mask_card_number("1234-5678-9012-3456")
        assert masked == "1234-****-****-3456"

    def test_mask_card_with_spaces(self):
        """Card with spaces should be masked correctly."""
        masked = mask_card_number("1234 5678 9012 3456")
        assert masked == "1234-****-****-3456"

    def test_short_card_returns_as_is(self):
        """Card with fewer than 8 digits should return unchanged."""
        short_card = "1234567"
        masked = mask_card_number(short_card)
        assert masked == short_card

    def test_already_masked_card(self):
        """Already masked card should be re-masked (keeps first/last 4)."""
        masked = mask_card_number("1234-****-****-5678")
        assert masked == "1234-****-****-5678"

    def test_15_digit_amex(self):
        """15-digit AMEX card should be handled."""
        masked = mask_card_number("371449635398431")
        assert masked == "3714-****-****-8431"

    def test_empty_string(self):
        """Empty string should return empty."""
        masked = mask_card_number("")
        assert masked == ""


# ============================================================
# format_amount Tests
# ============================================================


class TestFormatAmount:
    """Tests for Korean Won amount formatting."""

    def test_format_small_amount(self):
        """Small amounts should be formatted correctly."""
        assert format_amount(100) == "100원"
        assert format_amount(999) == "999원"

    def test_format_thousands(self):
        """Thousands should have comma separator."""
        assert format_amount(1000) == "1,000원"
        assert format_amount(9900) == "9,900원"
        assert format_amount(29900) == "29,900원"

    def test_format_large_amounts(self):
        """Large amounts should have multiple separators."""
        assert format_amount(1000000) == "1,000,000원"
        assert format_amount(9999999) == "9,999,999원"

    def test_format_zero(self):
        """Zero should be formatted correctly."""
        assert format_amount(0) == "0원"


# ============================================================
# normalize_phone Tests
# ============================================================


class TestNormalizePhone:
    """Tests for phone number normalization."""

    def test_normalize_dashed_phone(self):
        """Dashed phone number should be normalized."""
        assert normalize_phone("010-1234-5678") == "01012345678"

    def test_normalize_spaced_phone(self):
        """Spaced phone number should be normalized."""
        assert normalize_phone("010 1234 5678") == "01012345678"

    def test_normalize_international_format(self):
        """International format should be normalized."""
        assert normalize_phone("+82 10 1234 5678") == "821012345678"

    def test_normalize_mixed_format(self):
        """Mixed format should be normalized."""
        assert normalize_phone("+82-10-1234-5678") == "821012345678"

    def test_already_normalized(self):
        """Already normalized number should remain unchanged."""
        assert normalize_phone("01012345678") == "01012345678"

    def test_normalize_with_parentheses(self):
        """Number with parentheses should be normalized."""
        assert normalize_phone("(010) 1234-5678") == "01012345678"

    def test_empty_string(self):
        """Empty string should return empty."""
        assert normalize_phone("") == ""
