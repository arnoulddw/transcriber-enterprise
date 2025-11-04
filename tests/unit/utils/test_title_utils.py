import pytest

from app.utils import title_utils


def test_clean_generated_title_strips_quotes_and_whitespace():
    raw_title = "  \"  Weekly sync   overview \"  "
    cleaned = title_utils.clean_generated_title(raw_title)
    assert cleaned == "Weekly sync overview"


@pytest.mark.parametrize(
    ("raw_title", "expected"),
    [
        ("Temas urgentes por línea de negocio", "Temas urgentes línea negocio"),
        ("Quarterly financial results discussion", "Quarterly financial results discussion"),
        ("Revisión de estrategias de ventas", "Revisión de estrategias de ventas"),
    ],
)
def test_enforce_word_limit_drops_filler_words(raw_title, expected):
    cleaned = title_utils.clean_generated_title(raw_title)
    adjusted = title_utils.enforce_word_limit(cleaned)
    assert adjusted == expected
    assert len(adjusted.split()) <= title_utils.TITLE_MAX_WORDS


def test_enforce_word_limit_truncates_when_needed():
    raw_title = "Deep dive into product roadmap priorities"
    cleaned = title_utils.clean_generated_title(raw_title)
    adjusted = title_utils.enforce_word_limit(cleaned, max_words=3)
    assert adjusted == "Deep dive product"
    assert len(adjusted.split()) == 3
