"""
Utility functions for EasyPay payment integration.

Usage:
    from easypay.utils import get_client_ip, get_device_type_code

    # In your view
    client_ip = get_client_ip(request)
    device_type_code = get_device_type_code(request)  # "PC" or "MOBILE"
"""

import re
from typing import Literal

from django.http import HttpRequest


def get_client_ip(request: HttpRequest) -> str:
    """
    Extract the real client IP address from request.

    Handles CloudFlare → Nginx → Django proxy chain correctly.

    Priority:
        1. CF-Connecting-IP (CloudFlare)
        2. X-Real-IP (Nginx)
        3. X-Forwarded-For (Proxy chain, first IP)
        4. REMOTE_ADDR (Direct connection)

    Args:
        request: Django HttpRequest object

    Returns:
        Client IP address as string, or empty string if not found
    """
    # CloudFlare
    ip = request.META.get("HTTP_CF_CONNECTING_IP")
    if ip:
        return ip.strip()

    # Nginx
    ip = request.META.get("HTTP_X_REAL_IP")
    if ip:
        return ip.strip()

    # Proxy chain (first IP is the real client)
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    # Direct connection
    return request.META.get("REMOTE_ADDR", "")


def get_device_type_code(request: HttpRequest) -> Literal["PC", "MOBILE"]:
    """
    Determine device type code from User-Agent header.

    EasyPay requires deviceTypeCode to be "PC" or "MOBILE" (string, not numeric code).

    Args:
        request: Django HttpRequest object

    Returns:
        "PC" or "MOBILE" (EasyPay deviceTypeCode)
    """
    user_agent = request.META.get("HTTP_USER_AGENT", "").lower()

    # Mobile device patterns
    mobile_patterns = [
        "mobile",
        "android",
        "iphone",
        "ipad",
        "ipod",
        "blackberry",
        "windows phone",
        "opera mini",
        "opera mobi",
        "webos",
        "palm",
        "symbian",
        "nokia",
        "samsung",
        "lg-",
        "htc",
        "mot-",
        "sonyericsson",
    ]

    for pattern in mobile_patterns:
        if pattern in user_agent:
            return "MOBILE"

    return "PC"


def get_user_agent(request: HttpRequest) -> str:
    """
    Extract User-Agent header from request.

    Args:
        request: Django HttpRequest object

    Returns:
        User-Agent string, truncated to 500 chars for database storage
    """
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    # Truncate to fit in CharField(max_length=500)
    return user_agent[:500]


def mask_card_number(card_no: str) -> str:
    """
    Mask card number for display, keeping first 4 and last 4 digits.

    Args:
        card_no: Full or partially masked card number

    Returns:
        Masked card number (e.g., "1234-****-****-5678")

    Examples:
        >>> mask_card_number("1234567890123456")
        "1234-****-****-3456"
        >>> mask_card_number("1234-5678-9012-3456")
        "1234-****-****-3456"
    """
    # Handle None or empty string
    if not card_no:
        return ""

    # Remove any existing formatting
    digits = re.sub(r"[^0-9]", "", card_no)

    if len(digits) < 8:
        return card_no  # Return as-is if too short

    first4 = digits[:4]
    last4 = digits[-4:]

    return f"{first4}-****-****-{last4}"


def format_amount(amount: int) -> str:
    """
    Format amount with Korean Won symbol and thousand separators.

    Args:
        amount: Amount in KRW (integer)

    Returns:
        Formatted string (e.g., "29,900원")

    Examples:
        >>> format_amount(29900)
        "29,900원"
        >>> format_amount(1000000)
        "1,000,000원"
    """
    return f"{amount:,}원"


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number to digits only (Korean format).

    Args:
        phone: Phone number in any format

    Returns:
        Phone number with only digits (e.g., "01012345678")

    Examples:
        >>> normalize_phone("010-1234-5678")
        "01012345678"
        >>> normalize_phone("+82 10 1234 5678")
        "821012345678"
    """
    return re.sub(r"[^0-9]", "", phone)
