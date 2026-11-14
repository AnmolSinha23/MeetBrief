"""Search normalization, filtering, clustering, and ranking step."""

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from dateutil import parser as date_parser
import tldextract

from app.clients.search import SearchClient
from app.models import ResolvedEntity, Source, Window

logger = logging.getLogger(__name__)

PRIMARY_DOMAINS: Set[str] = {
    "prnewswire.com",
    "businesswire.com",
    "globenewswire.com",
}

# Offline tldextract to prevent runtime downloads
_tld_extractor = tldextract.TLDExtract(suffix_list_urls=())

def get_registered_domain(url: str) -> str:
    """Extracts registered domain (e.g. stripe.com) using offline tldextract."""
    extracted = _tld_extractor(url)
    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}".lower()
    return urlparse(url).netloc.lower()

def canonicalize_url(raw_url: str) -> str:
    """Normalizes URL by stripping www, fragments, trailing slashes, and utm_* params."""
    try:
        parsed = urlparse(raw_url)
        # Strip www.
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]

        # Strip utm_* and tracking params
        query_params = parse_qsl(parsed.query, keep_blank_values=False)
        filtered_params = [
            (k, v)
            for k, v in query_params
            if not k.lower().startswith("utm_")
            and k.lower() not in ("ref", "fbclid", "gclid", "source")
        ]
        new_query = urlencode(filtered_params)

        # Normalize path: remove trailing slash unless root
        path = parsed.path
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        # Reconstruct without fragment
        clean_url = urlunparse((parsed.scheme or "https", netloc, path, parsed.params, new_query, ""))
        return clean_url
    except Exception:
        return raw_url.rstrip("/")

def parse_source_date(item: Dict[str, Any]) -> Optional[date]:
    """Tolerantly parses published date from Tavily item."""
    for field in ("published_date", "published_time", "date", "publishedDate"):
        val = item.get(field)
        if val and isinstance(val, str) and val.strip():
            try:
                dt = date_parser.parse(val)
                return dt.date()
            except Exception:
                continue
    return None

def compute_title_jaccard(title_a: str, title_b: str) -> float:
    """Computes word token Jaccard similarity between two titles."""
    words_a = set(re.findall(r"\b\w{3,}\b", title_a.lower()))
    words_b = set(re.findall(r"\b\w{3,}\b", title_b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union > 0 else 0.0

async def normalize_sources(
    raw_items: List[Dict[str, Any]],
    entity: ResolvedEntity,
    window: Window,
    search_client: Optional[SearchClient] = None,
    enable_extract: bool = True,
    extract_top_n: int = 4,
) -> Tuple[List[Source], Dict[str, Any]]:
    """Normalizes, filters, dedupes, clusters, ranks, and enriches search items.

    Returns:
        Tuple of (list_of_Sources, normalize_trace_stats).
    """
    total_raw = len(raw_items)
    dropped_out_of_window = 0
    dropped_wrong_entity = 0
    dropped_duplicates = 0

    # Build entity search terms for relevance filter
    entity_terms = {entity.canonical_name.lower()}
    for alias in entity.aliases:
        if alias and len(alias.strip()) >= 2:
            entity_terms.add(alias.lower())

    # 1. Canonicalize & Dedupe exact URLs
    seen_urls: Dict[str, Dict[str, Any]] = {}
    for item in raw_items:
        raw_url = item.get("url") or ""
        if not raw_url:
            continue
        canon_url = canonicalize_url(raw_url)
        item["_canon_url"] = canon_url

        existing = seen_urls.get(canon_url)
        if existing is not None:
            dropped_duplicates += 1
            # Keep the one with higher score
            if float(item.get("score", 0.0)) > float(existing.get("score", 0.0)):
                seen_urls[canon_url] = item
        else:
            seen_urls[canon_url] = item

    deduped_items = list(seen_urls.values())

    # 2. Parse dates, apply window filter & relevance filter
    filtered_items: List[Dict[str, Any]] = []
    for item in deduped_items:
        title = item.get("title", "")
        content = item.get("content", "")
        is_background = item.get("_is_background", False)
        item_date = parse_source_date(item)
        item["_parsed_date"] = item_date

        # Window filter
        in_window = True
        if item_date is not None:
            if item_date < window.start or item_date > window.end:
                if not is_background:
                    dropped_out_of_window += 1
                    continue
                else:
                    in_window = False
        else:
            # Undated
            in_window = False

        item["_in_window"] = in_window

        # Relevance filter
        combined_text = (title + " " + content).lower()
        is_relevant = any(term in combined_text for term in entity_terms)
        if not is_relevant and not is_background:
            dropped_wrong_entity += 1
            continue

        filtered_items.append(item)

    # 3. Dedupe & Cluster near-duplicates
    cluster_counter = 1
    clusters: List[Tuple[int, str, str]] = []  # (cluster_id, domain, title)
    clustered_items: List[Dict[str, Any]] = []

    for item in filtered_items:
        url = item["_canon_url"]
        domain = get_registered_domain(url)
        title = item.get("title", "")

        assigned_cluster = None
        for cid, c_domain, c_title in clusters:
            # Same domain + exact title or title Jaccard >= 0.8
            jaccard = compute_title_jaccard(title, c_title)
            if (domain == c_domain and title.lower() == c_title.lower()) or jaccard >= 0.8:
                assigned_cluster = cid
                break

        if assigned_cluster is None:
            assigned_cluster = cluster_counter
            clusters.append((cluster_counter, domain, title))
            cluster_counter += 1

        item["_cluster_id"] = assigned_cluster
        item["_domain"] = domain
        clustered_items.append(item)

    # 4. Tag Primary Sources
    official_domain_clean = (
        get_registered_domain(f"https://{entity.official_domain}") if entity.official_domain else None
    )

    for item in clustered_items:
        domain = item["_domain"]
        url_path = urlparse(item["_canon_url"]).path.lower()

        is_primary = False
        if official_domain_clean and domain == official_domain_clean:
            is_primary = True
        elif domain.endswith(".gov") or domain.endswith(".sec.gov"):
            is_primary = True
        elif domain in PRIMARY_DOMAINS:
            is_primary = True
        elif official_domain_clean and official_domain_clean in domain:
            if any(p in url_path for p in ("/press", "/newsroom", "/investors", "/blog")):
                is_primary = True

        item["_is_primary"] = is_primary

    # 5. Rank by score and recency; keep top 20
    def rank_key(it: Dict[str, Any]):
        score = float(it.get("score", 0.0))
        d = it.get("_parsed_date") or date.min
        return (score, d)

    clustered_items.sort(key=rank_key, reverse=True)
    top_items = clustered_items[:20]

    # 6. Extract top N in-window sources if enabled
    if enable_extract and search_client and top_items:
        in_window_urls = [it["_canon_url"] for it in top_items if it.get("_in_window")][:extract_top_n]
        if in_window_urls:
            try:
                extracted = await search_client.extract(in_window_urls)
                extract_map = {
                    canonicalize_url(e.get("url", "")): e.get("raw_content", "")
                    for e in extracted
                    if e.get("raw_content")
                }
                for it in top_items:
                    c_url = it["_canon_url"]
                    if c_url in extract_map and extract_map[c_url]:
                        # Replace snippet with truncated extracted text up to 2000 chars
                        it["content"] = extract_map[c_url][:2000]
            except Exception as e:
                logger.warning(f"Extract step failed: {e}")

    # 7. Assign IDs S1..Sn
    sources: List[Source] = []
    for idx, it in enumerate(top_items, 1):
        snippet = it.get("content", "")
        # Limit snippet size: <= 700 chars normally, up to 2000 if extracted
        max_snippet_len = 2000 if len(snippet) > 700 else 700
        sources.append(
            Source(
                id=f"S{idx}",
                url=it["_canon_url"],
                title=it.get("title", ""),
                domain=it["_domain"],
                published_date=it["_parsed_date"],
                snippet=snippet[:max_snippet_len],
                score=float(it.get("score", 0.0)),
                is_primary=it["_is_primary"],
                cluster_id=it["_cluster_id"],
                category=it.get("_category", "general"),
                in_window=it["_in_window"],
            )
        )

    trace_stats = {
        "raw_count": total_raw,
        "dropped_duplicates": dropped_duplicates,
        "dropped_out_of_window": dropped_out_of_window,
        "dropped_wrong_entity": dropped_wrong_entity,
        "kept_count": len(sources),
        "in_window_count": sum(1 for s in sources if s.in_window),
        "primary_count": sum(1 for s in sources if s.is_primary),
    }

    return sources, trace_stats
