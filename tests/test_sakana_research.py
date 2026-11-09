import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sakana_research


class SakanaResearchTests(unittest.TestCase):
    def test_research_card_uses_visible_publication_date(self):
        response = Mock()
        response.content = b'''
        <article data-labels="research">
          <header>
            <h1><a href="/example-research/">Example research result</a></h1>
            <time datetime="2026-10-19T15:00:00Z">October 20, 2026</time>
          </header>
        </article>
        '''
        with patch.object(sakana_research.requests, "get", return_value=response):
            rows = list(sakana_research.entries({"url": "https://sakana.ai/"}))
        self.assertEqual(rows, [
            ("https://sakana.ai/example-research/", "Example research result", "2026-10-20")
        ])


if __name__ == "__main__":
    unittest.main()
