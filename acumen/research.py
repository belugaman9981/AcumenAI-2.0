from urllib.parse import urlparse, parse_qs, unquote
import html
import re
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; AcumenAI/0.4.2; local research agent)"

ACTION_PREFIXES = [
    r"^\s*research\s+",
    r"^\s*search(?:\s+the\s+web)?\s+(?:for\s+)?",
    r"^\s*find\s+(?:me\s+)?(?:information\s+about\s+|info\s+about\s+)?",
    r"^\s*look\s+up\s+",
    r"^\s*lookup\s+",
    r"^\s*help\s+me\s+with\s+my\s+homework\s*:\s*",
]

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

def _normalize_query(query):
    q = _clean(query)
    for pattern in ACTION_PREFIXES:
        q2 = re.sub(pattern, "", q, flags=re.I)
        if q2 != q:
            q = q2.strip()
            break
    return q or query

class WebResearcher:
    def __init__(self, config):
        self.config = config
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})

    def _ddg_html_search(self, query):
        results = []
        try:
            r = self.s.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                timeout=self.config["request_timeout"],
            )
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
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
                    "provider": "DuckDuckGo",
                })
                if len(results) >= self.config["max_search_results"]:
                    break
        except Exception:
            pass
        return results

    def _ddg_instant_answer(self, query):
        try:
            r = self.s.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "no_redirect": 1,
                    "skip_disambig": 1,
                },
                timeout=self.config["request_timeout"],
            )
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []

        out = []
        abstract = _clean(data.get("AbstractText", ""))
        abstract_url = data.get("AbstractURL", "")
        heading = _clean(data.get("Heading", "")) or query
        if abstract:
            out.append({
                "title": heading,
                "url": abstract_url or "https://duckduckgo.com/",
                "snippet": abstract,
                "prefetched_text": abstract,
                "provider": data.get("AbstractSource") or "DuckDuckGo",
            })

        answer = _clean(data.get("Answer", ""))
        if answer:
            out.append({
                "title": heading,
                "url": "https://duckduckgo.com/",
                "snippet": answer,
                "prefetched_text": answer,
                "provider": "DuckDuckGo",
            })
        return out

    def _wikipedia_search(self, query, limit=3):
        """Use MediaWiki's API as a reliable fallback and text source."""
        try:
            r = self.s.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": limit,
                    "format": "json",
                    "utf8": 1,
                },
                timeout=self.config["request_timeout"],
            )
            r.raise_for_status()
            rows = r.json().get("query", {}).get("search", [])
        except Exception:
            return []

        results = []
        for row in rows:
            title = row.get("title", "")
            if not title:
                continue
            try:
                er = self.s.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "prop": "extracts",
                        "explaintext": 1,
                        "exintro": 1,
                        "exsentences": 8,
                        "titles": title,
                        "format": "json",
                        "redirects": 1,
                    },
                    timeout=self.config["request_timeout"],
                )
                er.raise_for_status()
                pages = er.json().get("query", {}).get("pages", {})
                page = next(iter(pages.values()), {})
                extract = _clean(page.get("extract", ""))
            except Exception:
                extract = ""

            url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
            results.append({
                "title": title,
                "url": url,
                "snippet": extract[:700],
                "prefetched_text": extract,
                "provider": "Wikipedia",
            })
        return results

    def search(self, query):
        query = _normalize_query(query)
        gathered = []

        # Start with sources that return text directly and are less brittle.
        gathered.extend(self._ddg_instant_answer(query))
        gathered.extend(self._wikipedia_search(query, limit=3))
        gathered.extend(self._ddg_html_search(query))

        # De-duplicate URLs while preserving order.
        out = []
        seen = set()
        for item in gathered:
            key = item.get("url") or item.get("title")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
            if len(out) >= self.config["max_search_results"]:
                break
        return out

    def fetch_text(self, url):
        r = self.s.get(
            url,
            timeout=self.config["request_timeout"],
            allow_redirects=True,
        )
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
            if 25 <= len(s.strip()) <= 520
        ]

    @staticmethod
    def _terms(query):
        stop = {
            "the","a","an","is","are","was","were","to","of","for","and","or",
            "in","on","at","me","my","find","search","look","up","research","please",
            "what","who","where","when","why","how","do","does","did","tell","about",
            "information","info","explain"
        }
        return {
            x for x in re.findall(r"[a-z0-9'-]+", query.lower())
            if len(x) > 2 and x not in stop
        }

    @staticmethod
    def _question_type(query):
        q = _normalize_query(query).lower()
        if q.startswith("why ") or " why " in q:
            return "why"
        if q.startswith("who "):
            return "who"
        if q.startswith("where "):
            return "where"
        if q.startswith("when "):
            return "when"
        if q.startswith("how "):
            return "how"
        return "what"

    def rank_sentences(self, query, page_text, limit=3):
        terms = self._terms(query)
        qtype = self._question_type(query)
        ranked = []

        intent_markers = {
            "why": ("because", "due to", "caused by", "results from", "reason", "scattering"),
            "who": ("invented", "created", "developed", "founded", "by "),
            "where": ("located", "situated", "in ", "at "),
            "when": ("in 19", "in 20", "year", "date", "founded"),
            "how": ("by ", "through", "using", "process", "works"),
            "what": (" is ", " are ", "refers to", "means", "defined as"),
        }

        for index, sentence in enumerate(self._sentences(page_text)):
            low = sentence.lower()
            hits = sum(1 for t in terms if t in low)
            if not hits and terms:
                continue

            score = hits / max(1, len(terms))
            if any(marker in low for marker in intent_markers[qtype]):
                score += 0.24
            if index < 3:
                score += 0.08
            # Prefer readable explanatory sentences.
            if 50 <= len(sentence) <= 300:
                score += 0.05
            ranked.append((score, sentence))

        ranked.sort(key=lambda x: x[0], reverse=True)

        seen = set()
        out = []
        for score, sentence in ranked:
            key = re.sub(r"\W+", " ", sentence.lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            out.append({"score": round(score, 3), "text": sentence})
            if len(out) >= limit:
                break
        return out

    def research(self, query):
        normalized_query = _normalize_query(query)
        search_results = self.search(normalized_query)
        evidence = []

        for result in search_results[: self.config["max_pages_to_scrape"]]:
            page_text = result.get("prefetched_text", "")
            if not page_text:
                try:
                    page_text = self.fetch_text(result["url"])
                except Exception:
                    page_text = ""

            ranked = self.rank_sentences(normalized_query, page_text, limit=3)

            if not ranked and result.get("snippet"):
                ranked = self.rank_sentences(
                    normalized_query,
                    result["snippet"],
                    limit=2
                )
                if not ranked:
                    ranked = [{"score": .2, "text": result["snippet"]}]

            if ranked:
                evidence.append({
                    "title": result["title"],
                    "url": result["url"],
                    "provider": result.get("provider", ""),
                    "sentences": ranked,
                })

        candidates = []
        for source_index, source in enumerate(evidence):
            for s in source["sentences"]:
                # Tiny preference for source diversity/order.
                score = s["score"] - (source_index * 0.005)
                candidates.append(
                    (score, s["text"], source["title"], source["url"])
                )
        candidates.sort(key=lambda x: x[0], reverse=True)

        answer_sentences = []
        seen = set()
        for score, sentence, title, url in candidates:
            normalized = re.sub(r"\W+", " ", sentence.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            answer_sentences.append(sentence)
            if len(answer_sentences) >= 3:
                break

        if not answer_sentences:
            return {
                "ok": False,
                "answer": (
                    "I searched the web, but I couldn't extract enough readable "
                    "information to answer that."
                ),
                "sources": search_results[:5],
                "confidence": 0.2,
            }

        return {
            "ok": True,
            "answer": " ".join(answer_sentences),
            "sources": [
                {
                    "title": x["title"],
                    "url": x["url"],
                    "provider": x.get("provider", ""),
                }
                for x in evidence[:5]
            ],
            "confidence": min(.92, .5 + .12 * len(evidence)),
        }
