from dataclasses import dataclass

from app.core.constants import RecommendedAction, RiskLevel


@dataclass(frozen=True)
class ScoreResult:
    score: int
    level: RiskLevel
    recommended_action: RecommendedAction


def _minimum_score(risk_types: set[str]) -> int:
    minimum = 0
    if "resident_id" in risk_types:
        minimum = max(minimum, 40)
    if "card_number" in risk_types:
        minimum = max(minimum, 35)
    if "verification_code" in risk_types:
        minimum = max(minimum, 30)
    if {"verification_code", "urgency"}.issubset(risk_types):
        minimum = 70
    if {"money_transfer", "institution_impersonation"}.issubset(risk_types):
        minimum = 70
    if {"apk_installation", "suspicious_url"}.issubset(risk_types):
        minimum = 70
    privacy_types = {"resident_id", "card_number", "account_number", "verification_code"}
    if len(privacy_types.intersection(risk_types)) >= 2:
        minimum = 70
    return minimum


def calculate_score(
    *,
    local_score: int,
    rule_score: int,
    llm_score: int | None,
    llm_confidence: float | None,
    risk_types: list[str],
    sensitivity: str = "normal",
) -> ScoreResult:
    if llm_score is None:
        raw_score = local_score * 0.60 + rule_score * 0.40
    else:
        llm_weight = 0.40
        if llm_confidence is not None and llm_confidence < 0.5:
            llm_weight *= max(llm_confidence, 0.0) / 0.5
        raw_score = local_score * 0.35 + rule_score * 0.25 + llm_score * llm_weight

    score = max(round(raw_score), _minimum_score(set(risk_types)))
    score += {"low": -10, "normal": 0, "high": 10}.get(sensitivity, 0)
    score = min(max(score, 0), 100)

    if score >= 70:
        level = RiskLevel.DANGER
        action = (
            RecommendedAction.SUGGEST_CANCEL
            if score >= 90
            else RecommendedAction.CONFIRM_BEFORE_SEND
        )
    elif score >= 40:
        level = RiskLevel.WARNING
        action = RecommendedAction.SHOW_WARNING
    else:
        level = RiskLevel.SAFE
        action = RecommendedAction.ALLOW

    return ScoreResult(score=score, level=level, recommended_action=action)
