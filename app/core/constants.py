from enum import StrEnum


class RiskLevel(StrEnum):
    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"


class UserAction(StrEnum):
    NONE = "none"
    CONTINUE = "continue"
    CANCEL = "cancel"
    EDIT = "edit"


class RecommendedAction(StrEnum):
    ALLOW = "allow"
    SHOW_WARNING = "show_warning"
    CONFIRM_BEFORE_SEND = "confirm_before_send"
    SUGGEST_CANCEL = "suggest_cancel"
    LOCAL_FALLBACK = "local_fallback"


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FALLBACK = "fallback"
    FAILED = "failed"


RISK_TYPES = {
    "resident_id",
    "card_number",
    "account_number",
    "verification_code",
    "phone_number",
    "suspicious_url",
    "apk_installation",
    "money_transfer",
    "institution_impersonation",
    "family_impersonation",
    "urgency",
    "secrecy_request",
    "repeated_pressure",
    "social_engineering",
    "unknown",
}
