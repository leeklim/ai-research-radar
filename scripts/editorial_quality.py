"""Conservative editorial checks for the mixed research-team directories.

Pass the official article's description and article text when the headline
resembles an operational announcement or user guide. Do not use site-wide
navigation, footers, related-post recommendations or search-engine snippets.
"""
import re
from urllib.parse import urlsplit


# Independently checked article-level exceptions. These URLs are effective
# during migration and scheduled collection even when an old card lacks text.
REVIEWED = {
    ("1", "/constitution"): "model behaviour policy",
    ("1", "/research/introducing-anthropic-science"): "announcement of a new editorial channel",
    ("1", "/research/economic-index-survey-announcement"): "survey launch and participation FAQ; no survey findings",
    ("1", "/research/desktop-extensions"): "software packaging, installation and configuration guide",
    ("1", "/research/claude-code-best-practices"): "product usage documentation",
    ("1", "/research/building-effective-agents"): "engineering patterns and practitioner guidance",
    ("1", "/research/demystifying-evals-for-ai-agents"): "tutorial on building evaluations",
    ("1", "/research/trustworthy-agents"): "five practical safety principles for deploying agents",
    ("1", "/research/equipping-agents-for-the-real-world-with-agent-skills"): "product integration guide for Agent Skills",
    ("1", "/research/effective-context-engineering-for-ai-agents"): "practitioner guide to managing agent context",
    ("1", "/research/writing-tools-for-agents"): "tool-writing tutorial with a cookbook and implementation tips",
    ("17", "/research/ai-code-of-conduct"): "enterprise AI behaviour policy",
    ("17", "/research/best-practices-for-deploying-language-models"): "deployment policy recommendations",
    ("12", "/deepseek-ai/open-infra-index"): "multi-project release index rather than an individual study",
}

# Do not infer "non-research" from 'blog', 'engineering', 'policy', 'release'
# or 'introducing'. Apply this only to a clearly identified higher-risk type.
PROMOTIONAL = re.compile(
    r"\b(?:introducing|launching|announcing)\b.{0,65}\b(?:our (?:new )?(?:blog|newsletter)|"
    r"fellowship program|grant program|office hours|call for (?:papers|proposals)|"
    r"(?:registration|applications) for)\b|"
    r"\b(?:we(?:'re| are) hiring|open positions|join our team|applications are open|"
    r"announces? (?:a |our )?(?:partnership|funding round)|raises? \$[\d.]+[bm]?\b|"
    r"terms of service|privacy policy|code of conduct|one-click installation|"
    r"getting started with|installation guide|setup guide|register for our)\b",
    re.I,
)
RESULT = re.compile(
    r"\b(?:we|our (?:study|experiment|analysis|evaluation|team)|this (?:study|paper))\s+"
    r"(?:have\s+)?(?:measur\w*|evaluat\w*|benchmark\w*|tested|find|found|show\w*|"
    r"demonstrat\w*|compar\w*|replicat\w*|investigat\w*|report(?:ed)?|"
    r"introduc\w* (?:a |an )?(?:model|dataset|algorithm|method|benchmark|architecture))\b|"
    r"\b(?:our results|experimental results|ablation study|we discovered|"
    r"we have discovered|we share (?:high-level )?results|we present (?:a|an|the) (?:new )?"
    r"(?:model|dataset|algorithm|method|benchmark|architecture))\b",
    re.I,
)
GUIDE_OR_NEWS_SUMMARY = re.compile(
    r"^(?:a |an |our )?(?:new blog (?:about|covering)|step-by-step (?:guide|tutorial)|"
    r"(?:practical )?guidance (?:on|for|from)|tips and tricks (?:for|to)|"
    r"(?:five|six|seven|ten|\d+) principles for (?:building|deploying)|"
    r"(?:a )?blog post covering tips and tricks)\b",
    re.I,
)


def exclusion_reason(row, description="", article_text=""):
    source=str(row["source"])
    # Constrain reviewed exceptions to the exact verified source + URL path.
    url=urlsplit(row["url"])
    expected={"1":"anthropic.com","17":"ai21.com","12":"github.com"}
    if url.hostname and url.hostname.removeprefix("www.")==expected.get(source):
        known=REVIEWED.get((source,url.path.rstrip("/")))
        if known:
            return known
    if source not in {"0","1","10","17","20","21"}:
        return None
    headline=row.get("title","")
    if not PROMOTIONAL.search(headline) and not GUIDE_OR_NEWS_SUMMARY.search(description.strip()):
        return None
    if RESULT.search(" ".join((description,article_text))):
        return None
    return "operational announcement or guide without evidence of a study"
