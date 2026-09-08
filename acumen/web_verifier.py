from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from urllib.parse import quote
import re
import requests
from bs4 import BeautifulSoup
from .text import canonical_entity
from .storage import utc_now

@dataclass
class VerificationResult:
    status: str
    confidence: float
    claimed_subject: str
    relation: str
    claimed_object: str
    corrected_subject: str | None
    corrected_object: str | None
    evidence: list
    checked_at: str
    message: str

    def to_dict(self):
        return asdict(self)

class WikipediaVerifier:
    API = "https://en.wikipedia.org/w/api.php"
    BASE = "https://en.wikipedia.org/wiki/"

    def __init__(self, timeout=10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AcumenAI/0.3 educational-verifier (local user agent)"
        })

    def _search_title(self, query):
        r = self.session.get(
            self.API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "utf8": 1,
                "srlimit": 3,
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        items = r.json().get("query", {}).get("search", [])
        return items[0]["title"] if items else None

    def _fetch_page(self, title):
        url = self.BASE + quote(title.replace(" ", "_"))
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return url, BeautifulSoup(r.text, "html.parser")

    @staticmethod
    def _clean(text):
        text = re.sub(r"\[[^\]]+\]", "", text or "")
        return " ".join(text.split()).strip()

    def _intro_text(self, soup):
        body = soup.select_one(".mw-parser-output")
        if not body:
            return ""
        parts = []
        for p in body.find_all("p", recursive=False):
            txt = self._clean(p.get_text(" ", strip=True))
            if txt:
                parts.append(txt)
            if len(" ".join(parts)) > 1800:
                break
        return " ".join(parts)

    def _infobox_value(self, soup, labels):
        for row in soup.select("table.infobox tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            label = self._clean(th.get_text(" ", strip=True)).lower()
            if any(label == x or label.startswith(x + " ") for x in labels):
                return self._clean(td.get_text(" ", strip=True))
        return None

    @staticmethod
    def _similar(a, b):
        a = canonical_entity(a)
        b = canonical_entity(b)
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        if a in b or b in a:
            return 0.92
        return SequenceMatcher(None, a, b).ratio()

    def verify(self, claim):
        try:
            if claim["relation"] == "capital_of":
                return self._verify_capital(claim)
            return self._verify_general(claim)
        except Exception as e:
            return VerificationResult(
                status="uncertain",
                confidence=0.0,
                claimed_subject=claim["subject"],
                relation=claim["relation"],
                claimed_object=claim["object"],
                corrected_subject=None,
                corrected_object=None,
                evidence=[],
                checked_at=utc_now(),
                message=f"Verification failed: {type(e).__name__}: {e}",
            )

    def _verify_capital(self, claim):
        country = canonical_entity(claim["object"])
        title = self._search_title(country)
        if not title:
            return self._uncertain(claim, "I couldn't find a matching country page.")

        url, soup = self._fetch_page(title)
        capital = self._infobox_value(soup, {"capital"})
        if not capital:
            return self._uncertain(claim, "I found the page but couldn't extract a capital.")

        # Strip common notes/coordinates and take the first textual capital.
        actual = re.split(r"\s{2,}|\n|Coordinates?:", capital, maxsplit=1)[0].strip()
        claimed = claim["subject"]
        similarity = self._similar(claimed, actual)

        evidence = [{
            "source": "Wikipedia",
            "title": title,
            "url": url,
            "field": "Capital",
            "value": actual,
        }]

        if similarity >= 0.86:
            return VerificationResult(
                "verified", 0.96,
                claim["subject"], claim["relation"], claim["object"],
                canonical_entity(actual), canonical_entity(title),
                evidence, utc_now(),
                f"{actual} is listed as the capital of {title}.",
            )

        return VerificationResult(
            "rejected", 0.96,
            claim["subject"], claim["relation"], claim["object"],
            canonical_entity(actual), canonical_entity(title),
            evidence, utc_now(),
            f"The source lists {actual}, not {claim['subject']}, as the capital of {title}.",
        )

    def _verify_general(self, claim):
        subject = canonical_entity(claim["subject"])
        obj = canonical_entity(claim["object"])
        title = self._search_title(subject)
        if not title:
            return self._uncertain(claim, "I couldn't find a page for the subject.")

        url, soup = self._fetch_page(title)
        intro = self._intro_text(soup)
        intro_lower = canonical_entity(intro)
        obj_tokens = [x for x in re.findall(r"[a-z0-9'-]+", obj) if len(x) > 2]
        hit_ratio = (
            sum(1 for token in obj_tokens if token in intro_lower) / len(obj_tokens)
            if obj_tokens else 0.0
        )

        evidence = [{
            "source": "Wikipedia",
            "title": title,
            "url": url,
            "snippet": intro[:700],
        }]

        if hit_ratio >= 0.75:
            return VerificationResult(
                "verified", 0.82,
                claim["subject"], claim["relation"], claim["object"],
                canonical_entity(title), obj,
                evidence, utc_now(),
                "The subject page contains strong supporting evidence for the claimed object.",
            )

        return VerificationResult(
            "uncertain", 0.45,
            claim["subject"], claim["relation"], claim["object"],
            canonical_entity(title), None,
            evidence, utc_now(),
            "I found the subject page, but the page text did not provide strong enough support.",
        )

    def _uncertain(self, claim, message):
        return VerificationResult(
            "uncertain", 0.20,
            claim["subject"], claim["relation"], claim["object"],
            None, None, [], utc_now(), message,
        )
