from datetime import datetime

from dealbot.utils.ua import build_fallback_summary, format_deadline, truncate_text


def test_truncate_text_avoids_hard_cut() -> None:
    text = "\u041f\u0435\u0440\u0448\u0435 \u0440\u0435\u0447\u0435\u043d\u043d\u044f. \u0414\u0440\u0443\u0433\u0435 \u0440\u0435\u0447\u0435\u043d\u043d\u044f \u0434\u0443\u0436\u0435 \u0434\u043e\u0432\u0433\u0435 \u0456 \u043f\u0440\u043e\u0434\u043e\u0432\u0436\u0443\u0454\u0442\u044c\u0441\u044f \u0449\u0435 \u0442\u0440\u043e\u0445\u0438, \u0449\u043e\u0431 \u043f\u0440\u043e\u0439\u0442\u0438 \u043b\u0456\u043c\u0456\u0442 \u0441\u0438\u043c\u0432\u043e\u043b\u0456\u0432. \u0422\u0440\u0435\u0442\u0454 \u0440\u0435\u0447\u0435\u043d\u043d\u044f."
    assert truncate_text(text, max_length=60).endswith(".") or truncate_text(text, max_length=60).endswith("...")


def test_format_deadline_uses_ukrainian_month() -> None:
    formatted = format_deadline(datetime(2026, 3, 18, 14, 30))
    assert formatted == "18 \u0431\u0435\u0440\u0435\u0437\u043d\u044f 2026, 14:30"


def test_build_fallback_summary_mentions_title() -> None:
    summary = build_fallback_summary("Game", ["Action"], ["Coop"], False)
    assert "Game" in summary


def test_build_fallback_summary_localizes_focus_terms() -> None:
    summary = build_fallback_summary("Game", ["Action"], ["Co-op", "Adventure"], True, source="epic")
    lowered = summary.lower()
    assert "\u043a\u043e\u043e\u043f\u0435\u0440\u0430\u0442\u0438\u0432" in lowered
    assert "co-op" not in lowered
    assert "action" not in lowered