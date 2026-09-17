from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import yaml

from acumen.config import DEFAULTS, load_config
from acumen.knowledge import KnowledgeStore, matching_answers, merge_candidate, select_answer


NOW = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
QUESTION = "What is the capital of Canada?"


def answer(**metadata):
    return {
        "query": QUESTION,
        "answer": "Ottawa is the capital of Canada.",
        "confidence": .8,
        "kind": "research",
        "sources": [{"url": "https://example.org/canada"}],
        **metadata,
    }


@pytest.mark.parametrize("age, reusable", [
    (timedelta(days=29), True),
    (timedelta(days=30), True),
    (timedelta(days=30, microseconds=1), False),
    (timedelta(minutes=-5), True),
    (timedelta(minutes=-5, microseconds=-1), False),
])
def test_reuse_has_an_inclusive_age_limit_and_bounded_clock_skew(age, reusable):
    item = answer(researched_at=(NOW - age).isoformat())
    assert (select_answer([item], QUESTION, now=NOW) is item) == reusable


@pytest.mark.parametrize("timestamp", [
    "2026-09-16T12:00:00Z",
    "2026-09-16T05:00:00-07:00",
    "2026-09-16T20:00:00+08:00",
    "2026-09-16T12:00:00",
])
def test_iso_dates_use_equivalent_utc_times(timestamp):
    item = answer(researched_at=timestamp)
    assert select_answer([item], QUESTION, now=NOW) is item
    assert select_answer([item], QUESTION, now=NOW.isoformat()) is item


@pytest.mark.parametrize("timestamp", [None, "", "invalid", 123, [], {}, "9999-99-99"])
def test_invalid_research_date_cannot_fall_back_to_recent_save_date(timestamp):
    item = answer(researched_at=timestamp, updated_at=NOW.isoformat(), created_at=NOW.isoformat())
    assert select_answer([item], QUESTION, now=NOW) is None


def test_missing_dates_abstain_but_remain_available_for_matching_and_browsing(tmp_path):
    item = answer(id="legacy")
    store = KnowledgeStore(tmp_path)
    store._save({"version": 1, "items": [item]})
    assert store.lookup(QUESTION, now=NOW) is None
    assert matching_answers(store.all(), QUESTION) == [item]
    assert store.search(QUESTION)[0]["id"] == "legacy"


def test_legacy_dates_fall_back_in_order_without_hiding_expiry():
    fresh = NOW.isoformat()
    stale = (NOW - timedelta(days=31)).isoformat()
    assert select_answer([answer(created_at=fresh)], QUESTION, now=NOW)
    assert select_answer([answer(updated_at=fresh, created_at=stale)], QUESTION, now=NOW)
    assert select_answer([answer(updated_at=stale, created_at=fresh)], QUESTION, now=NOW) is None
    assert select_answer([answer(researched_at=stale, updated_at=fresh)], QUESTION, now=NOW) is None


def test_conflicting_old_answer_still_prevents_automatic_reuse():
    old = answer(answer="Toronto", researched_at=(NOW - timedelta(days=300)).isoformat())
    fresh = answer(researched_at=NOW.isoformat())
    assert select_answer([old, fresh], QUESTION, now=NOW) is None
    assert matching_answers([old, fresh], QUESTION) == [old, fresh]


@pytest.mark.parametrize("kind", ["math", "homework"])
def test_symbolic_math_does_not_expire(kind):
    item = answer(kind=kind, query="2+2", answer="4", sources=[{"url": "local://sympy"}])
    assert select_answer([item], "2+2", now=NOW) is item
    item["researched_at"] = "2000-01-01T00:00:00Z"
    assert select_answer([item], "2+2", now=NOW) is item
    item["sources"] = [{"url": "https://example.org/math"}]
    assert select_answer([item], "2+2", now=NOW) is None


def test_research_cannot_claim_the_symbolic_math_exemption():
    item = answer(sources=[{"url": "local://sympy"}])
    assert select_answer([item], QUESTION, now=NOW) is None


def test_direct_add_assigns_research_date_and_lookup_uses_the_age_policy(tmp_path):
    store = KnowledgeStore(tmp_path)
    with patch("acumen.knowledge.utc_now", return_value=NOW.isoformat()):
        saved = store.add(answer())
    assert saved["researched_at"] == NOW.isoformat()
    assert store.lookup(QUESTION, now=NOW)["id"] == saved["id"]
    assert store.lookup(QUESTION, now=NOW + timedelta(days=31)) is None
    assert store.lookup(QUESTION, max_age_days=60, now=NOW + timedelta(days=31))["id"] == saved["id"]


def test_save_and_usage_cannot_refresh_research_age(tmp_path):
    store = KnowledgeStore(tmp_path)
    old = (NOW - timedelta(days=31)).isoformat()
    with patch("acumen.knowledge.utc_now", return_value=NOW.isoformat()):
        saved = store.add(answer(researched_at=old))
        assert saved["updated_at"] == NOW.isoformat()
        store.record_use(saved["id"])
        store.add(answer())
        store.add(answer(updated_at=NOW.isoformat()))
    persisted = store.all()[0]
    assert persisted["researched_at"] == old
    assert persisted["use_count"] == 1
    assert persisted["last_used_at"] == NOW.isoformat()
    assert store.lookup(QUESTION, now=NOW) is None


@pytest.mark.parametrize("metadata", [{}, {"created_at": "2000-01-01T00:00:00Z"}])
def test_merging_legacy_record_does_not_turn_a_save_into_new_research(tmp_path, metadata):
    store = KnowledgeStore(tmp_path)
    original = answer(id="legacy", **metadata)
    store._save({"version": 1, "items": [original]})
    with patch("acumen.knowledge.utc_now", return_value=NOW.isoformat()):
        store.add(answer())
    assert store.lookup(QUESTION, now=NOW) is None


def test_first_save_preserves_pending_legacy_age(tmp_path):
    store = KnowledgeStore(tmp_path)
    old = (NOW - timedelta(days=31)).isoformat()
    with patch("acumen.knowledge.utc_now", return_value=NOW.isoformat()):
        saved = store.add(answer(created_at=old))
    assert saved["researched_at"] == old
    assert store.lookup(QUESTION, now=NOW) is None


@pytest.mark.parametrize("timestamp", [None, "invalid", ""])
def test_direct_add_preserves_explicit_invalid_research_date(tmp_path, timestamp):
    store = KnowledgeStore(tmp_path)
    with patch("acumen.knowledge.utc_now", return_value=NOW.isoformat()):
        saved = store.add(answer(researched_at=timestamp))
    assert saved["researched_at"] == timestamp
    assert store.lookup(QUESTION, now=NOW) is None


def test_fresh_evidence_can_refresh_an_answer_but_older_snapshots_cannot(tmp_path):
    store = KnowledgeStore(tmp_path)
    old = answer(researched_at=(NOW - timedelta(days=40)).isoformat())
    fresh = answer(researched_at=NOW.isoformat(), sources=[{"url": "https://example.org/new"}])
    with patch("acumen.knowledge.utc_now", return_value=NOW.isoformat()):
        first = store.add(old)
        updated = store.add(fresh)
        store.add(old)
    assert updated["id"] == first["id"]
    assert store.all()[0]["researched_at"] == NOW.isoformat()
    assert len(store.all()[0]["sources"]) == 2
    assert store.lookup(QUESTION, now=NOW)


@pytest.mark.parametrize("timestamp", ["invalid", None, "2200-01-01T00:00:00Z"])
def test_invalid_or_far_future_incoming_date_cannot_refresh_existing(timestamp):
    old_date = (NOW - timedelta(days=40)).isoformat()
    with patch("acumen.knowledge.utc_now", return_value=NOW.isoformat()):
        merged = merge_candidate(answer(researched_at=old_date), answer(researched_at=timestamp))
    assert merged["researched_at"] == old_date


@pytest.mark.parametrize("value", [0, -1, None, True, "bad", [], {}, float("nan"), float("inf")])
def test_invalid_age_settings_use_the_safe_default(tmp_path, value):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"learning": {"recheck_after_days": value}}), encoding="utf-8")
    assert load_config(path)["learning"]["recheck_after_days"] == 30
    old = answer(researched_at=(NOW - timedelta(days=31)).isoformat())
    assert select_answer([old], QUESTION, max_age_days=value, now=NOW) is None


@pytest.mark.parametrize("learning", [None, "invalid", []])
def test_invalid_learning_section_uses_the_safe_default(tmp_path, learning):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"learning": learning}), encoding="utf-8")
    assert load_config(path)["learning"]["recheck_after_days"] == 30


def test_valid_age_setting_is_respected_without_mutating_defaults(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("learning:\n  recheck_after_days: 0.5\n", encoding="utf-8")
    config = load_config(path)
    assert config["learning"]["recheck_after_days"] == .5
    assert DEFAULTS["learning"]["recheck_after_days"] == 30
    item = answer(researched_at=(NOW - timedelta(hours=13)).isoformat())
    assert select_answer([item], QUESTION, max_age_days=.5, now=NOW) is None
    assert select_answer([item], QUESTION, max_age_days="1", now=NOW) is item
