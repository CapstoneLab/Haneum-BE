import re
from dataclasses import dataclass

from app.schemas.analysis import ContextMessage

URL_RE = re.compile(r"https?://[^\s]+|\b(?:bit\.ly|tinyurl\.com|url\.kr)/[^\s]+", re.I)
APK_RE = re.compile(r"\.apk\b|원격\s*제어|앱\s*설치|어플\s*설치|프로그램\s*설치", re.I)
TRANSFER_RE = re.compile(r"송금|입금|이체|보내\s*줘|돈\s*보내|계좌로", re.I)
INSTITUTION_RE = re.compile(r"검찰|경찰|금융감독원|금감원|은행|국세청|공공기관", re.I)
FAMILY_RE = re.compile(r"엄마|아빠|아들|딸|손자|손녀|가족|지인|휴대폰.*고장", re.I)
URGENCY_RE = re.compile(r"지금|즉시|당장|빨리|긴급|급해|오늘\s*안에", re.I)
SECRECY_RE = re.compile(r"비밀|말하지\s*마|알리면\s*안|혼자만|보안상", re.I)
PRESSURE_RE = re.compile(r"계속.*요구|반드시|무조건|안\s*하면|큰일", re.I)
VERIFICATION_RE = re.compile(r"인증\s*(?:번호|코드)|OTP|보안\s*코드", re.I)


@dataclass(frozen=True)
class RuleResult:
    score: int
    risk_types: list[str]
    reason: str


def _add_type(types: list[str], value: str) -> None:
    if value not in types:
        types.append(value)


def analyze_rules(input_text: str, context_messages: list[ContextMessage]) -> RuleResult:
    context = "\n".join(item.text for item in context_messages)
    combined = f"{context}\n{input_text}" if context else input_text
    score = 0
    types: list[str] = []

    if URL_RE.search(combined):
        _add_type(types, "suspicious_url")
        score += 10
    if APK_RE.search(combined):
        _add_type(types, "apk_installation")
        score += 15
    if TRANSFER_RE.search(combined):
        _add_type(types, "money_transfer")
        score += 20
    if INSTITUTION_RE.search(combined):
        _add_type(types, "institution_impersonation")
        score += 15
    if FAMILY_RE.search(combined):
        _add_type(types, "family_impersonation")
        score += 15
    if URGENCY_RE.search(combined):
        _add_type(types, "urgency")
        score += 10
    if SECRECY_RE.search(combined):
        _add_type(types, "secrecy_request")
        score += 10
    if PRESSURE_RE.search(combined):
        _add_type(types, "repeated_pressure")
        score += 10
    if VERIFICATION_RE.search(combined):
        _add_type(types, "verification_code")
        score += 15

    social_signals = {
        "money_transfer",
        "institution_impersonation",
        "family_impersonation",
        "urgency",
        "secrecy_request",
        "repeated_pressure",
        "verification_code",
    }.intersection(types)
    if len(social_signals) >= 2:
        _add_type(types, "social_engineering")
        score += 10

    if not types:
        return RuleResult(score=0, risk_types=[], reason="규칙 기반 위험 요소가 없습니다.")

    labels = {
        "suspicious_url": "의심 링크",
        "apk_installation": "앱 설치 유도",
        "money_transfer": "송금 요구",
        "institution_impersonation": "기관 사칭 표현",
        "family_impersonation": "가족·지인 사칭 표현",
        "urgency": "긴급성 표현",
        "secrecy_request": "비밀 유지 요구",
        "repeated_pressure": "반복 압박",
        "verification_code": "인증번호 요구",
        "social_engineering": "사회공학적 유도",
    }
    detected = ", ".join(labels[item] for item in types[:4])
    return RuleResult(
        score=min(score, 100),
        risk_types=types[:10],
        reason=f"{detected}이(가) 감지되었습니다.",
    )
