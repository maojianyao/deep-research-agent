"""Document identity helpers shared by search, extraction, and rendering."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "yclid", "ref", "ref_src", "spm", "from", "source",
}


def clean_text(text: str | None) -> str:
    """Collapse whitespace so search snippets do not create noisy paragraphs."""
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_url(url: str) -> str:
    """Remove tracking parameters, fragments, and a trailing slash."""
    url = str(url or "")
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
              if key.lower() not in _TRACKING_PARAMS]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(query), ""))


def infer_source_type_from_domain(url: str) -> str:
    """从 URL 域名推断基础来源类型，为下游证据审查与排序提供第一手依据。"""
    try:
        domain = urlsplit(str(url or "")).netloc.removeprefix("www.").lower()
    except Exception:
        return "unknown"
    if not domain:
        return "unknown"

    if any(domain.endswith(suf) for suf in (".gov", ".gov.cn", ".mil", ".gov.uk", ".europa.eu", ".who.int", ".un.org")):
        return "government"
    if any(domain.endswith(suf) for suf in (".edu", ".edu.cn", ".ac.uk", ".ac.jp", "ac.cn")):
        return "academic"
    if any(sub in domain for sub in ("arxiv.org", "biorxiv.org", "medrxiv.org",
                                     "researchgate.net", "ssrn.com", "neurips.cc",
                                     "psyarxiv.com", "core.ac.uk", "biomedcentral.com",
                                     "pubscholar.cn", "cnki.net", "springer.com",
                                     "sciencedirect.com"
                                     )):
        return "academic"
    if any(sub in domain for sub in ("reuters.com", "bloomberg.com", "ft.com", "wsj.com", "caixin.com", "bbc.com", "apnews.com", "xinhuanet.com", "cctv.com", "nytimes.com")):
        return "news_major"
    if any(sub in domain for sub in ("github.com", "sec.gov", "huggingface.co")):
        return "primary"
    return "unknown"


def document_keys(url: str, title: str) -> tuple[str, str | None]:
    """Return URL and same-domain title keys used to detect duplicate documents."""
    url_key = normalize_url(url)
    normalized_title = "".join(ch for ch in (title or "").lower() if ch.isalnum())
    domain = urlsplit(url_key).netloc.removeprefix("www.").lower()
    # Very short titles such as "Home" are not unique enough to deduplicate.
    title_key = f"title:{domain}:{normalized_title}" if len(normalized_title) >= 8 else None
    return url_key, title_key
