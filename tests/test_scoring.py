from app.core.constants import RecommendedAction, RiskLevel
from app.services.scoring import calculate_score


def test_uses_documented_weighted_formula() -> None:
    result = calculate_score(
        local_score=30,
        rule_score=20,
        llm_score=80,
        llm_confidence=0.9,
        risk_types=["urgency"],
    )

    assert result.score == 48
    assert result.level == RiskLevel.WARNING
    assert result.recommended_action == RecommendedAction.SHOW_WARNING


def test_critical_combination_applies_minimum_score() -> None:
    result = calculate_score(
        local_score=30,
        rule_score=10,
        llm_score=None,
        llm_confidence=None,
        risk_types=["verification_code", "urgency"],
    )

    assert result.score == 70
    assert result.level == RiskLevel.DANGER


def test_sensitivity_is_clamped() -> None:
    result = calculate_score(
        local_score=100,
        rule_score=100,
        llm_score=100,
        llm_confidence=1.0,
        risk_types=["urgency"],
        sensitivity="high",
    )
    assert result.score == 100
