from app.global_ranker import FixedGlobalRanker, NullGlobalRanker


def test_fixed_global_ranker_only_marks_top_one_percent_as_strong():
    ranker = FixedGlobalRanker(probability=0.92, percentile=0.995)
    result = ranker.score(None)

    assert result["is_strong_global_signal"] is True
    assert result["global_score"] == 1.0
    assert result["global_signal_level"] == "STRONG_GLOBAL_SIGNAL"


def test_null_global_ranker_is_safe_and_unavailable():
    result = NullGlobalRanker().score(None)

    assert result["status"] == "unavailable"
    assert result["global_score"] == 0.0
    assert result["reason_codes"] == []
