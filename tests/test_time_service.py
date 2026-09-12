from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import requests

from acumen.client import AcumenClient
from acumen.config import DEFAULTS
from acumen.router import route
from acumen.time_intent import extract_time_location, is_time_request
from acumen.time_service import TimeProvider


SHENZHEN = {
    "name": "Shenzhen", "admin1": "Guangdong", "country": "China",
    "country_code": "CN", "timezone": "Asia/Shanghai",
}
QUESTION = "what is the time in shenzhen right now?"


@pytest.mark.parametrize("query, city", [
    (QUESTION, "shenzhen"),
    ("what time is it in Vancouver BC?", "Vancouver BC"),
    ("what's the time in New York now?", "New York"),
    ("Can you please tell me the current time in London?", "London"),
    ("Time in Shenzhen, China, please", "Shenzhen, China"),
    ("Shenzhen time", "Shenzhen"),
    ("current time in UTC", "UTC"),
])
def test_clock_requests_are_routed_before_research(query, city):
    assert route(query).kind == "time"
    assert route(query).force_web
    assert extract_time_location(query) == city


@pytest.mark.parametrize("query", [
    "What is time?", "What is time dilation?", "How does time travel work?",
    "Who invented time?", "Explain time", "Tell me about time",
    "What time does the flight leave?", "What is the best time to visit Shenzhen?",
    "What is the time difference between Shenzhen and Vancouver?",
])
def test_other_time_topics_keep_their_meaning(query):
    assert not is_time_request(query)
    assert route(query).kind != "time"


def test_exact_screenshot_question_bypasses_bad_saved_answer_and_does_not_learn(tmp_path):
    client = AcumenClient("local", tmp_path, DEFAULTS)
    processor = client.local_processor
    processor.time_provider.now = lambda: datetime(2026, 9, 9, 1, 4, 5, tzinfo=timezone.utc)
    client.knowledge.add({"query": QUESTION, "answer": "China Southern Airlines Flight 3456 was a flight."})
    try:
        with patch("acumen.time_service.WeatherProvider.geocode", return_value=SHENZHEN) as geocode, \
             patch.object(processor.researcher, "research", side_effect=AssertionError("article search must not run")):
            answer = client.chat(QUESTION)
            assert "9:04:05 AM" in answer
            assert "Shenzhen, Guangdong, China" in answer
            assert "UTC+08:00" in answer
            assert "Flight" not in answer
            processor.time_provider.now = lambda: datetime(2026, 9, 9, 1, 5, 6, tzinfo=timezone.utc)
            assert "9:05:06 AM" in client.chat(QUESTION)
            assert geocode.call_count == 1  # Reuse only the location, never the reading.
        assert processor.sessions.get(client.session_id)["candidates"] == []
        assert len(client.knowledge.all()) == 1  # Existing data was not deleted.
    finally:
        processor.close()


@pytest.mark.parametrize("task_type", ["time", "research", "knowledge_query"])
def test_worker_handles_clock_requests_from_older_clients(tmp_path, task_type):
    client = AcumenClient("local", tmp_path, DEFAULTS)
    processor = client.local_processor
    try:
        with patch("acumen.time_service.WeatherProvider.geocode", return_value=SHENZHEN), \
             patch.object(processor.researcher, "research", side_effect=AssertionError("unexpected research")):
            result = processor.process(task_type, {"query": QUESTION}, client.session_id)
        assert result["ok"] and result["kind"] == "time"
        assert result["learnable"] is False
        assert processor.sessions.get(client.session_id)["candidates"] == []
    finally:
        processor.close()


@pytest.mark.parametrize("month, expected_hour, expected_offset", [(1, 4, "-08:00"), (7, 5, "-07:00")])
def test_time_conversion_uses_daylight_saving_rules(month, expected_hour, expected_offset):
    place = {"name": "Vancouver", "admin1": "British Columbia", "country": "Canada",
             "country_code": "CA", "timezone": "America/Vancouver"}
    provider = TimeProvider(now=lambda: datetime(2026, month, 1, 12, tzinfo=timezone.utc))
    with patch("acumen.time_service.WeatherProvider.geocode", return_value=place):
        result = provider.from_text("what time is it in Vancouver BC?")
    assert result["ok"]
    assert datetime.fromisoformat(result["local_time"]).hour == expected_hour
    assert result["local_time"].endswith(expected_offset)


def test_local_date_rolls_forward_in_shenzhen():
    provider = TimeProvider(now=lambda: datetime(2026, 9, 9, 18, tzinfo=timezone.utc))
    with patch("acumen.time_service.WeatherProvider.geocode", return_value=SHENZHEN):
        result = provider.from_text(QUESTION)
    assert result["local_time"].startswith("2026-09-10T02:00:00")


@pytest.mark.parametrize("place", [None, {"name": "Shenzhen"}, dict(SHENZHEN, name="Shenzhuang")])
def test_missing_or_wrong_location_returns_clear_failure(place):
    with patch("acumen.time_service.WeatherProvider.geocode", return_value=place):
        result = TimeProvider().from_text(QUESTION)
    assert not result["ok"]
    assert "timezone" in result["answer"]
    assert not result["learnable"]


def test_network_failure_is_retryable_and_does_not_fall_back_to_articles():
    provider = TimeProvider()
    with patch("acumen.time_service.WeatherProvider.geocode", side_effect=[requests.Timeout(), SHENZHEN]):
        assert not provider.from_text(QUESTION)["ok"]
        assert provider.from_text(QUESTION)["ok"]


def test_timezone_input_needs_no_geocoding_and_missing_city_is_not_guessed():
    with patch("acumen.time_service.WeatherProvider.geocode", side_effect=AssertionError("no geocoding expected")):
        provider = TimeProvider(now=lambda: datetime(2026, 9, 9, 1, 4, 5, tzinfo=timezone.utc))
        assert "1:04:05 AM" in provider.from_text("time in UTC")["answer"]
        assert provider.from_text("time in Asia/Shanghai")["ok"]
        assert not provider.from_text("time in Invalid/Zone")["ok"]
        assert "Which city" in provider.from_text("what time is it?")["answer"]


def test_pi_sends_clock_task_to_local_worker(tmp_path):
    client = AcumenClient("pi", tmp_path, DEFAULTS)
    with patch.object(client.queue, "submit", return_value="clock-task") as submit, \
         patch.object(client.queue, "wait", return_value={"ok": True, "answer": "A current clock reading"}), \
         patch.object(client.queue, "consume"):
        assert client.chat(QUESTION) == "A current clock reading"
    submit.assert_called_once_with("time", {"query": QUESTION}, client.session_id)
