from urllib.parse import urlparse, parse_qs, unquote, quote, urlsplit, urlunsplit, parse_qsl, urlencode
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import html
import re
import threading
import time
import requests
from bs4 import BeautifulSoup
from .time_intent import is_time_request
from .router import requires_fresh_data
from .text import expand_contractions, tokens

UA = "Mozilla/5.0 (compatible; AcumenAI/0.4.2; local research agent)"

ACTION_PREFIXES = [
    r"^\s*research\s+",
    r"^\s*search(?:\s+the\s+web)?\s+(?:for\s+)?",
    r"^\s*find\s+(?:me\s+)?(?:information\s+about\s+|info\s+about\s+)?",
    r"^\s*look\s+up\s+",
    r"^\s*lookup\s+",
    r"^\s*help\s+me\s+with\s+my\s+homework\s*:\s*",
    r"^\s*(?:tell\s+me\s+about|explain|describe|what\s+about|info\s+on|information\s+on)\s+",
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
    q = re.sub(r"^(?:please\s+|(?:can|could|would) you\s+(?:please\s+)?)", "", q, flags=re.I)
    for pattern in ACTION_PREFIXES:
        q2 = re.sub(pattern, "", q, flags=re.I)
        if q2 != q:
            q = q2.strip()
            break
    return q or query

def _url_key(url):
    """Remove fragments and known tracking parameters, preserving page identity."""
    parts = urlsplit(_unwrap_ddg(url))
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/",
                       urlencode(query), ""))

def _volatile_query(query):
    return requires_fresh_data(query)

class WebResearcher:
    def __init__(self, config):
        self.config = dict(config)
        self._local = threading.local()
        self._lock = threading.RLock()
        self._sessions = []
        self._session_override = None
        self._cache = OrderedDict()
        self._cache_ttl = max(0, float(config.get("cache_ttl_seconds", 300)))
        self._cache_limit = max(0, int(config.get("cache_max_entries", 128)))
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, min(16, int(config.get("max_workers", 4)))),
            thread_name_prefix="acumen-fetch",
        )

    @property
    def s(self):
        # requests sessions carry mutable cookies: give each worker its own pool.
        if self._session_override is not None:
            return self._session_override
        if not hasattr(self._local, "session"):
            session = requests.Session()
            session.headers.update({"User-Agent": UA})
            self._local.session = session
            with self._lock:
                self._sessions.append(session)
        return self._local.session

    @s.setter
    def s(self, session):
        self._session_override = session

    def close(self):
        self._executor.shutdown(wait=True)
        with self._lock:
            for session in self._sessions:
                session.close()
            self._sessions.clear()
            self._cache.clear()

    def _cached(self, key):
        if not self._cache_ttl or not self._cache_limit:
            return None
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            expires, value = entry
            if time.monotonic() >= expires:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return deepcopy(value)

    def _remember(self, key, value):
        if not value or not self._cache_ttl or not self._cache_limit:
            return
        with self._lock:
            self._cache[key] = (time.monotonic() + self._cache_ttl, deepcopy(value))
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_limit:
                self._cache.popitem(last=False)

    def _parallel(self, calls):
        futures = [self._executor.submit(fn, *args) for fn, args in calls]
        results = []
        # Submission order keeps ranking stable even when requests finish out of order.
        for future in futures:
            try:
                results.append(future.result())
            except Exception:
                results.append(None)
        return results

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

        rows = [row for row in rows if row.get("title")][:limit]
        if not rows:
            return []
        pages = {}
        aliases = {}
        try:
            er = self.s.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query", "prop": "extracts", "explaintext": 1,
                    "exintro": 1, "exsentences": 8, "exlimit": "max",
                    "titles": "|".join(row["title"] for row in rows),
                    "format": "json", "redirects": 1,
                },
                timeout=self.config["request_timeout"],
            )
            er.raise_for_status()
            data = er.json().get("query", {})
            pages = {page.get("title"): page for page in data.get("pages", {}).values()}
            aliases = {row["from"]: row["to"] for row in
                       data.get("normalized", []) + data.get("redirects", [])}
        except Exception:
            pass

        results = []
        for row in rows:
            title = row["title"]
            seen = set()
            while title in aliases and title not in seen:
                seen.add(title)
                title = aliases[title]
            extract = _clean(pages.get(title, {}).get("extract", ""))
            snippet = _clean(BeautifulSoup(row.get("snippet", ""), "html.parser").get_text(" "))
            url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="()_")
            results.append({
                "title": title,
                "url": url,
                "snippet": extract[:700] or snippet,
                "prefetched_text": extract,
                "provider": "Wikipedia",
            })
        return results

    def search(self, query):
        query = _normalize_query(query)
        cache_key = ("search", query.casefold())
        use_cache = not _volatile_query(query)
        cached = self._cached(cache_key) if use_cache else None
        if cached is not None:
            return cached
        gathered = self._parallel([
            (self._ddg_instant_answer, (query,)),
            (self._wikipedia_search, (query, 3)),
            (self._ddg_html_search, (query,)),
        ])

        # De-duplicate URLs while preserving order.
        out = []
        seen = {}
        for original in [item for group in gathered if group for item in group]:
            item = dict(original)
            url = item.get("url", "")
            if not url.startswith(("http://", "https://")):
                continue
            key = _url_key(url)
            item["url"] = key
            if key in seen:
                old = seen[key]
                for field in ("prefetched_text", "snippet"):
                    if len(item.get(field, "")) > len(old.get(field, "")):
                        old[field] = item[field]
                continue
            seen[key] = item
            out.append(item)
        out = out[:max(0, int(self.config["max_search_results"]))]
        if use_cache:
            self._remember(cache_key, out)
        return out

    def fetch_text(self, url):
        cache_key = ("page", _url_key(url))
        use_cache = not getattr(self._local, "fresh", False)
        cached = self._cached(cache_key) if use_cache else None
        if cached is not None:
            return cached
        r = self.s.get(
            url,
            timeout=self.config["request_timeout"],
            allow_redirects=True,
            stream=True,
        )
        try:
            r.raise_for_status()
            content_type = r.headers.get("content-type", "").lower()
            if not any(kind in content_type for kind in ("text/html", "application/xhtml+xml", "text/plain")):
                return ""
            remaining = max(1, int(self.config.get("max_page_bytes", 524288)))
            chunks = []
            for chunk in r.iter_content(chunk_size=min(16384, remaining)):
                if not chunk:
                    continue
                chunks.append(chunk[:remaining])
                remaining -= len(chunks[-1])
                if remaining <= 0:
                    break
            raw = b"".join(chunks)
            if "text/plain" in content_type:
                text = raw.decode(r.encoding or "utf-8", errors="replace")
                text = "\n".join(_clean(line) for line in text.splitlines() if _clean(line))
            else:
                # BeautifulSoup can respect a page's charset even without an HTTP charset.
                encoding = r.encoding if "charset=" in content_type else None
                text = self._html_text(raw, encoding=encoding)
            text = text[:max(0, int(self.config["max_page_chars"]))]
        finally:
            r.close()
        if use_cache:
            self._remember(cache_key, text)
        return text

    @staticmethod
    def _html_text(text, encoding=None):
        soup = BeautifulSoup(text, "html.parser", from_encoding=encoding)
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "aside", "svg"]):
            tag.decompose()
        body = soup.select_one("article") or soup.select_one("main") or soup.body or soup
        parts = []
        seen = set()
        for tag in body.find_all(["p", "li", "blockquote"]):
            if tag.find(["p", "li", "blockquote"]):
                continue
            part = _clean(tag.get_text(" ", strip=True))
            key = part.casefold()
            if part and key not in seen:
                seen.add(key)
                parts.append(part)
        return "\n".join(parts) if parts else _clean(body.get_text(" ", strip=True))

    @staticmethod
    def _sentences(text):
        return [
            s.strip()
            for s in re.split(r"\n+|(?<=[.!?])\s+", text)
            if 25 <= len(s.strip()) <= 520
        ]

    @staticmethod
    def _terms(query):
        stop = {
            "the","a","an","is","are","was","were","to","of","for","and","or",
            "in","on","at","me","my","find","search","look","up","research","please",
            "what","who","where","when","why","how","do","does","did","tell","about",
            "information","info","explain","describe","could","would","you"
        }
        return {
            x for x in tokens(expand_contractions(query)) if x not in stop
        }

    @staticmethod
    def _question_type(query):
        q = expand_contractions(_normalize_query(query))
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
        if is_time_request(query):
            return []
        terms = self._terms(_normalize_query(query))
        qtype = self._question_type(query)
        creation_terms = {"invented", "created", "developed", "founded"}
        asks_creator = qtype == "who" and bool(terms & creation_terms)
        if asks_creator:
            terms -= creation_terms
        if qtype == "how":
            terms -= {"work", "works"}
        if not terms:
            return []
        anchors = {term for term in terms if any(c.isdigit() for c in term) or len(term) <= 2}
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
            sentence_terms = set(tokens(expand_contractions(sentence)))
            hits = len(terms & sentence_terms)
            coverage = hits / len(terms)
            # One place/name match is not enough to answer a multi-part question.
            if coverage < .6:
                continue
            # Version numbers and short names (AI, UK, C) must not disappear.
            if not anchors <= sentence_terms:
                continue
            if asks_creator and not (sentence_terms & creation_terms):
                continue
            if qtype == "why" and not re.search(
                r"\b(because|due to|causes?|caused|causing|results? from|results? in|"
                r"reason|leads? to|therefore|as a result|makes?|scatters?|scattering)\b",
                low,
            ):
                continue

            score = coverage
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

    def _page_text(self, result, fresh):
        if result.get("prefetched_text"):
            return result["prefetched_text"]
        self._local.fresh = fresh
        try:
            return self.fetch_text(result["url"])
        finally:
            self._local.fresh = False

    def research(self, query):
        normalized_query = _normalize_query(query)
        if is_time_request(normalized_query):
            return {
                "ok": False, "learnable": False,
                "answer": "A current clock reading is needed for that question; web articles cannot provide it.",
                "sources": [], "evidence": [], "confidence": 0.0,
            }
        search_results = self.search(normalized_query)
        evidence = []
        selected = search_results[:max(0, int(self.config["max_pages_to_scrape"]))]
        page_texts = self._parallel([
            (self._page_text, (result, _volatile_query(normalized_query)))
            for result in selected
        ])
        for result, page_text in zip(selected, page_texts):
            page_text = page_text or ""
            ranked = self.rank_sentences(normalized_query, page_text, limit=3)
            evidence_kind = "page"

            if not ranked and result.get("snippet"):
                ranked = self.rank_sentences(
                    normalized_query,
                    result["snippet"],
                    limit=2
                )
                # Snippets may be truncated or out of context: keep confidence modest.
                ranked = [dict(sentence, score=min(.35, sentence["score"])) for sentence in ranked]
                evidence_kind = "snippet"

            if ranked:
                evidence.append({
                    "title": result["title"],
                    "url": result["url"],
                    "provider": result.get("provider", ""),
                    "sentences": ranked,
                    "kind": evidence_kind,
                })

        candidates = []
        for source_index, source in enumerate(evidence):
            for s in source["sentences"]:
                # Tiny preference for source diversity/order.
                score = s["score"] - (source_index * 0.005)
                candidates.append((score, s["text"], source))
        candidates.sort(key=lambda x: x[0], reverse=True)

        answer_sentences = []
        answer_evidence = []
        answer_sources = []
        source_urls = set()
        seen = set()
        for score, sentence, source in candidates:
            normalized = re.sub(r"\W+", " ", sentence.lower()).strip()
            if normalized not in seen and len(answer_sentences) >= 3:
                continue
            if normalized not in seen:
                seen.add(normalized)
                answer_sentences.append(sentence)
            answer_evidence.append({
                "text": sentence, "url": source["url"], "title": source["title"],
                "score": round(score, 3),
                "kind": source["kind"],
            })
            if source["url"] not in source_urls:
                source_urls.add(source["url"])
                answer_sources.append({
                    "title": source["title"], "url": source["url"],
                    "provider": source.get("provider", ""),
                })

        if not answer_sentences:
            return {
                "ok": False,
                "answer": (
                    "I found no evidence that directly answers your question. "
                    "Try a more specific question or source."
                ),
                "sources": [],
                "searched_sources": search_results[:5],
                "learnable": False,
                "confidence": 0.2,
            }

        # Every selected passage needs page support before it can be learned.
        supported = {
            re.sub(r"\W+", " ", item["text"].lower()).strip()
            for item in answer_evidence if item["kind"] == "page"
        }
        learnable = seen <= supported and not _volatile_query(normalized_query)
        return {
            "ok": True,
            "answer": " ".join(answer_sentences),
            "sources": answer_sources,
            "evidence": answer_evidence,
            "learnable": learnable,
            "confidence": min(
                .9 if seen <= supported else .49,
                .4 + .1 * len({urlsplit(source["url"]).netloc for source in answer_sources})
                + .2 * min(1, max(item["score"] for item in answer_evidence)),
            ),
        }
