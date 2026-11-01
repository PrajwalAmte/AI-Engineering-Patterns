from dataclasses import replace
from datetime import date

from governance.model_card import EvalResult, ModelCard

TODAY = date(2026, 11, 1)

CARD = ModelCard(
    system="Support answer bot",
    owner="support-ai@acme",
    base_model="claude-sonnet-4-5-20250929",
    prompt_version="support-v14",
    changed_on=date(2026, 10, 1),
    intended_use=["Answer billing and shipping questions from the help center"],
    out_of_scope=["Legal, medical or tax advice", "Account changes"],
    limitations=["Help-center articles older than 90 days may be stale", "English only"],
    data_sources=["help-center export (daily)", "order status API (read-only)"],
    evals=[EvalResult("support-regression", "judge mean (1-4)", 3.42, date(2026, 10, 2), "support-v3 (412 cases)")],
    human_oversight="Refunds over $20 require agent approval; 1% of answers reviewed weekly.",
)


def test_complete_card_passes():
    assert CARD.problems(TODAY) == []


def test_missing_limitations_fails_the_build():
    assert "limitations is empty" in replace(CARD, limitations=[]).problems(TODAY)


def test_evals_must_postdate_the_last_change():
    changed = replace(CARD, prompt_version="support-v15", changed_on=date(2026, 10, 20))
    assert any("predates" in p for p in changed.problems(TODAY))


def test_stale_evals_fail():
    assert any("older than" in p for p in CARD.problems(date(2027, 3, 1)))


def test_model_aliases_are_rejected():
    assert any("alias" in p for p in replace(CARD, base_model="gpt-latest").problems(TODAY))


def test_renders_markdown_with_eval_table():
    md = CARD.to_markdown()
    assert md.startswith("# Model card: Support answer bot")
    assert "| support-regression | judge mean (1-4) | 3.42 |" in md
