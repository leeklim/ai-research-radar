import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect
import openai_publications
import requests


class OpenAIPublicationsTests(unittest.TestCase):
    def test_latest_cards_do_not_require_backfill_or_article_requests(self):
        source = dict(id="0", adapter="openai_publications",
                      url="https://openai.com/research/index/publication/")
        props = {"dynamicPageLists": [{"tabId": "publication", "pageQueries": [
            {"pageTypes": ["Article"], "categories": ["publication"]}]}],
            "children": [None, None, None, {"initialResults": [{"total": 212, "items": [
                {"slug": "index/new-paper", "title": "New paper",
                 "publicationDate": "2026-11-09", "categories": []}]}]}]}
        response = Mock()
        response.content = ("<script>self.__next_f.push(" +
                            json.dumps([1, json.dumps(props)]) + ");</script>").encode()
        session = Mock()
        session.get.return_value = response
        with patch.object(collect.requests, "Session") as factory:
            factory.return_value.__enter__.return_value = session
            with patch.object(collect, "verify_destination", side_effect=AssertionError("article requested")):
                result = collect.collect(source, {}, {})
        self.assertEqual(len(result[1]), 1)
        self.assertEqual(result[2], "")
        self.assertEqual(session.get.call_count, 1)

    def test_blocked_latest_index_is_reported_as_latest_failure(self):
        session = Mock()
        session.get.side_effect = requests.HTTPError("403 Forbidden")
        with self.assertRaisesRegex(ValueError, "최신 Publication 목록 확인 실패.*403"):
            list(openai_publications.visible_index(
                {"url": "https://openai.com/research/index/publication/"}, session))


if __name__ == "__main__":
    unittest.main()
