import re

RESIDENT_ID_RE = re.compile(r"(?<!\d)(\d{6})[-\s]?(\d{7})(?!\d)")
CARD_RE = re.compile(r"(?<!\d)(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})(?!\d)")
PHONE_RE = re.compile(r"(?<!\d)(01[016789])[-\s]?(\d{3,4})[-\s]?(\d{4})(?!\d)")
OTP_RE = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")
ACCOUNT_RE = re.compile(r"(?<!\d)(?:\d{2,6}[-\s]){1,3}\d{2,6}(?!\d)")

OTP_CONTEXT_RE = re.compile(r"인증\s*번호|인증\s*코드|보안\s*코드|OTP", re.IGNORECASE)
ACCOUNT_CONTEXT_RE = re.compile(r"계좌|송금|입금|이체", re.IGNORECASE)


class MaskingError(ValueError):
    pass


def extract_sensitive_values(text: str) -> list[str]:
    values: list[str] = []
    for pattern in (RESIDENT_ID_RE, CARD_RE, PHONE_RE):
        values.extend(match.group(0) for match in pattern.finditer(text))
    if OTP_CONTEXT_RE.search(text):
        values.extend(match.group(0) for match in OTP_RE.finditer(text))
    if ACCOUNT_CONTEXT_RE.search(text):
        values.extend(match.group(0) for match in ACCOUNT_RE.finditer(text))
    return list(dict.fromkeys(values))


def mask_sensitive_text(text: str) -> str:
    return _mask_sensitive_text(
        text,
        mask_otp=bool(OTP_CONTEXT_RE.search(text)),
        mask_account=bool(ACCOUNT_CONTEXT_RE.search(text)),
    )


def _mask_sensitive_text(text: str, *, mask_otp: bool, mask_account: bool) -> str:
    masked = RESIDENT_ID_RE.sub(lambda m: f"{m.group(1)}-{m.group(2)[0]}******", text)
    masked = CARD_RE.sub(lambda m: f"****-****-****-{m.group(4)}", masked)
    masked = PHONE_RE.sub(lambda m: f"{m.group(1)}-****-{m.group(3)}", masked)
    if mask_otp:
        masked = OTP_RE.sub(lambda m: "*" * len(m.group(1)), masked)
    if mask_account:
        masked = ACCOUNT_RE.sub(lambda m: "*" * len(m.group(0)), masked)
    return masked


def mask_sensitive_texts(texts: list[str]) -> list[str]:
    """Mask a related text batch before it crosses the external AI boundary."""
    combined = "\n".join(texts)
    mask_otp = bool(OTP_CONTEXT_RE.search(combined))
    mask_account = bool(ACCOUNT_CONTEXT_RE.search(combined))
    return [
        _mask_sensitive_text(text, mask_otp=mask_otp, mask_account=mask_account)
        for text in texts
    ]


def verify_and_mask(input_text: str, client_masked_text: str) -> str:
    sensitive_values = extract_sensitive_values(input_text)
    leaked = [value for value in sensitive_values if value and value in client_masked_text]
    if leaked:
        raise MaskingError("클라이언트 마스킹 결과에 민감정보가 남아 있습니다.")

    server_masked = mask_sensitive_text(input_text)
    if any(value in server_masked for value in sensitive_values):
        raise MaskingError("서버에서 민감정보를 안전하게 마스킹하지 못했습니다.")

    # 서버가 인식한 값은 반드시 서버 마스킹 결과를 사용한다. 그 외에는 클라이언트가
    # 이미 더 강하게 가린 문자열을 보존한다.
    return server_masked if sensitive_values else client_masked_text
