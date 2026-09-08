from urllib.parse import urlparse, parse_qs, unquote
import html
import re
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; AcumenAI/0.4; +local research agent)"

def _clean(text):
    return " ".join(html.unescape(text or "").split())

def _unwrap_ddg(url):
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    except Exception:
        pass
    return url

class WebResearcher:
    def __init__(self, config):
        self.config = config
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})

    def search(self, query):
        r = self.s.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            timeout=self.config["request_timeout"],
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for node in soup.select(".result"):
            a = node.select_one(".result__a")
            if not a:
                continue
            snippet = node.select_one(".result__snippet")
            url = _unwrap_ddg(a.get("href", ""))
            if not url.startswith(("http://", "https://")):
                continue
            results.append({
                "title": _clean(a.get_text(" ", strip=True)),
                "url": url,
                "snippet": _clean(snippet.get_text(" ", strip=True)) if snippet else "",
            })
            if len(results) >= self.config["max_search_results"]:
                break
        return results

    def fetch_text(self, url):
        r = self.s.get(url, timeout=self.config["request_timeout"], allow_redirects=True)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "text/html" not in content_type:
            return ""
        text = r.text[:self.config["max_page_chars"]]
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form"]):
            tag.decompose()
        return _clean(soup.get_text(" ", strip=True))

    @staticmethod
    def _sentences(text):
        return [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", text)
            if 35 <= len(s.strip()) <= 420
        ]

    @staticmethod
    def _terms(query):
        stop = {
            "the","a","an","is","are","was","were","to","of","for","and","or",
            "in","on","at","me","my","find","search","look","up","research","please",
            "what","who","where","when","why","how","do","does","did"
        }
        return {
            x for x in re.findall(r"[a-z0-9'-]+", query.lower())
            if len(x) > 2 and x not in stop
        }

    def rank_sentences(self, query, page_text, limit=3):
        terms = self._terms(query)
        ranked = []
        for sentence in self._sentences(page_text):
            low = sentence.lower()
            hits = sum(1 for t in terms if t in low)
            if hits:
                score = hits / max(1, len(terms))
                if any(x in low for x in (" is ", " are ", " because ", " means ", " refers to ")):
                    score += .08
                ranked.append((score, sentence))
        ranked.sort(key=lambda x: x[0], reverse=True)
        seen = set()
        out = []
        for score, sentence in ranked:
            key = sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({"score": round(score, 3), "text": sentence})
            if len(out) >= limit:
                break
        return out

    def research(self, query):
        search_results = self.search(query)
        evidence = []
        for result in search_results[: self.config["max_pages_to_scrape"]]:
            try:
                page_text = self.fetch_text(result["url"])
                ranked = self.rank_sentences(query, page_text, limit=2)
            except Exception:
                ranked = []

            if not ranked and result.get("snippet"):
                ranked = [{"score": .25, "text": result["snippet"]}]

            if ranked:
                evidence.append({
                    "title": result["title"],
                    "url": result["url"],
                    "sentences": ranked,
                })

        # Extractive answer: choose strongest non-duplicate evidence sentences.
        candidates = []
        for source in evidence:
            for s in source["sentences"]:
                candidates.append((s["score"], s["text"], source["title"], source["url"]))
        candidates.sort(key=lambda x: x[0], reverse=True)

        answer_sentences = []
        seen = set()
        for score, sentence, title, url in candidates:
            normalized = sentence.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            answer_sentences.append(sentence)
            if len(answer_sentences) >= 3:
                break

        if not answer_sentences:
            return {
                "ok": False,
                "answer": "I searched the web but couldn't extract a reliable answer.",
                "sources": search_results[:5],
                "confidence": 0.2,
            }

        return {
            "ok": True,
            "answer": " ".join(answer_sentences),
            "sources": [
                {"title": x["title"], "url": x["url"]}
                for x in evidence[:5]
            ],
            "confidence": min(.9, .45 + .12 * len(evidence)),
        }
