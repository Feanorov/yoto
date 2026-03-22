from datetime import datetime

from dealbot.utils.ua import build_fallback_summary, build_focus_text, format_deadline, truncate_text


def test_truncate_text_avoids_hard_cut() -> None:
    text = 'Перше речення. Друге речення дуже довге і продовжується ще трохи, щоб пройти ліміт символів. Третє речення.'
    truncated = truncate_text(text, max_length=60)
    assert truncated.endswith('.') or truncated.endswith('...')


def test_format_deadline_uses_ukrainian_month() -> None:
    formatted = format_deadline(datetime(2026, 3, 18, 14, 30))
    assert formatted == '18 березня 2026, 14:30'


def test_build_fallback_summary_mentions_title() -> None:
    summary = build_fallback_summary('Game', ['Action'], ['Coop'], False)
    assert 'Game' in summary


def test_build_fallback_summary_localizes_focus_terms() -> None:
    summary = build_fallback_summary('Game', [], ['Co-op', 'Adventure'], True, source='epic')
    lowered = summary.lower()
    assert 'кооператив' in lowered
    assert 'co-op' not in lowered
    assert 'adventure' not in lowered


def test_build_focus_text_localizes_new_editorial_terms() -> None:
    focus = build_focus_text(['tower defense', 'visual novel'], ['strategy'])
    lowered = focus.lower()
    assert 'тауер-дефенс' in lowered
    assert 'візуальні новели' in lowered
