from unittest.mock import patch

from acumen.client import AcumenClient
from acumen.config import DEFAULTS


def test_shared_question_words_do_not_reuse_a_different_country_answer(tmp_path):
    client = AcumenClient("local", tmp_path, DEFAULTS)
    client.knowledge.add({"query": "What is the capital of Canada?", "answer": "Ottawa"})
    try:
        with patch.object(client.local_processor.researcher, "research", return_value={"ok": True, "answer": "Paris"}) as research:
            assert client.chat("What is the capital of France?") == "Paris"
            research.assert_called_once()
        with patch.object(client.local_processor.researcher, "research", side_effect=AssertionError("unexpected research")):
            assert client.chat("  WHAT is the capital of Canada? ") == "Ottawa"
    finally:
        client.local_processor.close()


def test_live_queries_bypass_saved_answers_and_do_not_become_permanent_learning(tmp_path):
    client = AcumenClient("local", tmp_path, DEFAULTS)
    query = "Who is the prime minister today?"
    client.knowledge.add({"query": query, "answer": "An outdated answer"})
    try:
        with patch.object(client.local_processor.researcher, "research", return_value={"ok": True, "answer": "Fresh result"}) as research:
            assert client.chat(query) == "Fresh result"
            research.assert_called_once()
        assert client.session_store.get(client.session_id)["candidates"] == []
    finally:
        client.local_processor.close()
