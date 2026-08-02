from app.fusion import FusionConfig, FusionEngine


def test_critical_rule_overrides_weighted_score():
    engine = FusionEngine(
        FusionConfig(
            confirmation_threshold=0.95,
            critical_rule_override=True,
        )
    )
    result = engine.combine(
        global_result={"status": "success", "global_score": 0.0},
        personal_result={"personal_score": 0.10},
        rule_result={"rule_score": 0.90, "critical_rule_triggered": True},
    )

    assert result["requires_confirmation"] is True
    assert result["decision_factors"]["override_reason"] == "CRITICAL_RULE_OVERRIDE"


def test_strong_global_alone_does_not_force_confirmation():
    engine = FusionEngine()
    result = engine.combine(
        global_result={
            "status": "success",
            "global_score": 1.0,
            "is_strong_global_signal": True,
        },
        personal_result={"personal_score": 0.10},
        rule_result={"rule_score": 0.10, "critical_rule_triggered": False},
    )

    assert result["requires_confirmation"] is False


def test_strong_global_with_personal_support_requires_confirmation():
    engine = FusionEngine()
    result = engine.combine(
        global_result={
            "status": "success",
            "global_score": 1.0,
            "is_strong_global_signal": True,
        },
        personal_result={"personal_score": 0.70},
        rule_result={"rule_score": 0.20, "critical_rule_triggered": False},
    )

    assert result["requires_confirmation"] is True
    assert (
        result["decision_factors"]["override_reason"]
        == "STRONG_GLOBAL_WITH_PERSONAL_SUPPORT"
    )
