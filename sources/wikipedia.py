"""Real-knowledge grounding via Wikipedia — no API key, no new dependencies.

PROMETHEUS used to study facts the narrator *invented* from a topic name alone (and it
got things wrong). This fetches the real encyclopedia article for a subject so its study
set can be distilled from real text instead. Raw `requests` only, mirroring
llm/ollama_client.py's style. `fetch_real_text` NEVER raises — any miss returns None so
the caller falls back to the old invented-facts path (fictional subjects, offline, etc.).

Endpoints (validated live):
  * resolve subject -> article title via FULL-TEXT search (list=search), which handles
    descriptive phrases that the title-prefix `opensearch` endpoint misses;
  * skip disambiguation pages (pageprops has a "disambiguation" key);
  * fetch clean prose via prop=extracts&explaintext=1 (following redirects).
One cached fetch per subject, ever -> effectively no rate-limit concern.
"""
import re

import requests

import config

_API = "https://en.wikipedia.org/w/api.php"
_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "its", "de", "el",
         "s", "how", "why", "what", "about", "history", "field"}


def _sig_tokens(s):
    """Significant (>=3 char, non-stopword) tokens of a phrase, lowercased."""
    return [t for t in re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()
            if len(t) >= 3 and t not in _STOP]


def _covered(tokens, text):
    """Fraction of `tokens` that appear as a substring of `text` (handles compounds like
    'honeybees' vs 'honey'/'bee')."""
    return (sum(1 for t in tokens if t in text) / len(tokens)) if tokens else 0.0


def _relevant(subject, title, lead, thresh=0.5):
    """Is the resolved article actually ABOUT the subject? Accept if the title's significant
    words are largely reflected in the subject phrase (needing >=2 matched tokens so a lone
    generic word like 'generation' can't green-light 'Generation X'), OR the subject's
    significant words are largely reflected in the article title+lead. Rejects drift like
    'realism prompt engineering' -> 'AI art' or 'amazon acoustic ecology' -> 'Amazon river dolphin'."""
    subj_l = (subject or "").lower()
    blob = (title + " " + lead).lower()
    ttoks = _sig_tokens(title)
    tmatch = sum(1 for t in ttoks if t in subj_l)
    title_cov = (tmatch / len(ttoks)) if ttoks else 0.0
    subj_cov = _covered(_sig_tokens(subject), blob)
    return (tmatch >= 2 and title_cov >= thresh) or (subj_cov >= thresh)


def _get(params, timeout=20):
    r = requests.get(
        _API,
        params={**params, "format": "json"},
        headers={"User-Agent": config.WIKI_USER_AGENT},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def _search_titles(subject, limit=3):
    """Best-matching article titles for a (possibly descriptive) subject phrase."""
    hits = _get({"action": "query", "list": "search",
                 "srsearch": subject, "srlimit": limit}).get("query", {}).get("search", [])
    return [h["title"] for h in hits if h.get("title")]


def _is_disambiguation(title):
    pages = _get({"action": "query", "prop": "pageprops",
                  "titles": title, "redirects": 1}).get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    return "disambiguation" in (page.get("pageprops") or {})


def _extract(title):
    pages = _get({"action": "query", "prop": "extracts", "explaintext": 1,
                  "titles": title, "redirects": 1}).get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    return (page.get("extract") or "").strip()


# gemma3 tends to name subjects verbosely ("The Reconstruction of Roman Concrete"); the
# distinctive part ("Roman Concrete") searches far better, so we also try a cleaned query.
_OF_PREFIX = re.compile(
    r"^(the\s+)?(reconstruction|history|study|studies|mechanics|genetics|science|art|field|nature|"
    r"basics|fundamentals|overview|introduction|principles|analysis|exploration|understanding|"
    r"world|story|origins|evolution|role|use|uses|importance)\s+of\s+", re.I)
_LEAD_ARTICLE = re.compile(r"^(the|a|an)\s+", re.I)


def _clean_query(subject):
    q = _OF_PREFIX.sub("", subject.strip())
    q = _LEAD_ARTICLE.sub("", q)
    return q.strip()


def fetch_real_text(subject, max_chars=8000, min_chars=400):
    """Return (article_title, plaintext) grounded in Wikipedia, or None if nothing suitable.

    Tries the top hits for the raw subject AND a filler-stripped query, skipping disambiguation
    pages and stubs, and requiring topical relevance. Truncates long articles (~8k chars ≈ 2-3k
    tokens) so the distilling narrator stays within context.
    """
    subject = (subject or "").strip()
    if not subject:
        return None
    try:
        queries, cleaned = [subject], _clean_query(subject)
        if cleaned and cleaned.lower() != subject.lower():
            queries.append(cleaned)
        seen = set()
        for q in queries:
            for title in _search_titles(q):
                if title in seen:
                    continue
                seen.add(title)
                try:
                    if _is_disambiguation(title):
                        continue
                    text = _extract(title)
                except requests.RequestException:
                    continue
                # real article (not a stub) AND actually on-topic vs the ORIGINAL subject
                if len(text) >= min_chars and _relevant(subject, title, text[:800]):
                    return title, text[:max_chars]
        return None
    except Exception:                            # network/parse/anything -> graceful fallback
        return None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for s in ["the genetics of honeybees", "japanese kintsugi", "asdfqwer nonexistent zzz 999"]:
        res = fetch_real_text(s)
        if res:
            title, text = res
            print(f"\n[{s}] -> {title} ({len(text)} chars)\n  {text[:160]}…")
        else:
            print(f"\n[{s}] -> None (fallback)")
