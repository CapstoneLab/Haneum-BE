from dataclasses import dataclass

from app.core.constants import ConversationRiskStatus

PRIVACY_RISK_TYPES = {
    "resident_id",
    "card_number",
    "account_number",
    "verification_code",
}

CONFIRMED_COMBINATIONS = (
    {"verification_code", "urgency"},
    {"money_transfer", "institution_impersonation"},
    {"apk_installation", "suspicious_url"},
)


@dataclass(frozen=True)
class ConversationRiskDecision:
    status: ConversationRiskStatus
    suspicion_count: int
    peak_score: int
    risk_types: list[str]
    signal_counted: bool


def _has_confirmed_combination(risk_types: set[str]) -> bool:
    return any(group.issubset(risk_types) for group in CONFIRMED_COMBINATIONS)


def advance_conversation_risk(
    *,
    previous_status: ConversationRiskStatus,
    previous_suspicion_count: int,
    previous_peak_score: int,
    previous_risk_types: list[str],
    evidence_score: int,
    current_risk_types: list[str],
    count_current_signal: bool = True,
) -> ConversationRiskDecision:
    merged_types = list(dict.fromkeys([*previous_risk_types, *current_risk_types]))[:10]
    merged_type_set = set(merged_types)
    current_type_set = set(current_risk_types)
    peak_score = max(previous_peak_score, evidence_score)

    actionable_current_types = current_type_set - {"unknown"}
    current_is_suspicious = evidence_score >= 35 or bool(actionable_current_types)
    signal_counted = current_is_suspicious and count_current_signal
    suspicion_count = previous_suspicion_count + (1 if signal_counted else 0)

    should_confirm = (
        previous_status == ConversationRiskStatus.CONFIRMED
        or evidence_score >= 70
        or bool(PRIVACY_RISK_TYPES.intersection(current_type_set))
        or _has_confirmed_combination(merged_type_set)
        or suspicion_count >= 2
    )

    if should_confirm:
        status = ConversationRiskStatus.CONFIRMED
    elif previous_status == ConversationRiskStatus.WATCHING or current_is_suspicious:
        status = ConversationRiskStatus.WATCHING
    else:
        status = ConversationRiskStatus.NORMAL

    return ConversationRiskDecision(
        status=status,
        suspicion_count=suspicion_count,
        peak_score=peak_score,
        risk_types=merged_types,
        signal_counted=signal_counted,
    )
