import logging
import random
import re
import requests
import urllib3
from fastapi import HTTPException

# Prevent slow DNS/IPv6 timeouts on networks where IPv6 is unsupported
urllib3.util.connection.HAS_IPV6 = False

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

_session = requests.Session()
_session.headers.update(HEADERS)

BASE_URLS = [
    "https://api.mangadex.org",
    "https://api.mangadex.dev",
]
FALLBACK_COVER = "https://mangadex.org/_nuxt/img/cover-placeholder.d12c3c5.jpg"


# ---------------------------------------------------------------------------
# Network Fetchers
# ---------------------------------------------------------------------------

def _fetch_komiku(url: str, params: dict | None = None) -> str | None:
    try:
        r = _session.get(url, params=params, timeout=5)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        logger.warning("Komiku request error (%s): %s", url, e)
    return None


def _fetch_json(path: str, params: dict | list | None = None) -> dict:
    last_error = None
    for base in BASE_URLS:
        try:
            r = _session.get(f"{base}{path}", params=params, timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_error = str(e)
    raise HTTPException(status_code=502, detail={"error": "All MangaDex sources failed", "last_error": last_error})


# ---------------------------------------------------------------------------
# Komiku Helpers
# ---------------------------------------------------------------------------

def _parse_komiku_html(html: str) -> list[dict]:
    items = []
    # 1. Parse modern komiku.org article.ls2
    articles = re.findall(r'<article class="ls2">(.*?)</article>', html, re.DOTALL)
    if articles:
        flag_map = {"jp": "Manga", "kr": "Manhwa", "cn": "Manhua"}
        for art in articles:
            slug_m = re.search(r'href="/manga/([^/]+)/"', art)
            title_m = re.search(r'<h3><a[^>]*>(.*?)</a></h3>', art)
            type_flag = re.search(r'class="flag" src="/asset/img/(jp|kr|cn)\.png"', art)
            img_m = re.search(r'data-src="([^"]+)"', art) or re.search(r'src="([^"]+)"', art)
            genre_m = re.search(r'<span class="ls2t">(.*?)</span>', art)

            komik_type = flag_map.get(type_flag.group(1), "Manga") if type_flag else "Manga"
            tags = [komik_type]
            if genre_m and genre_m.group(1).strip():
                tags.append(genre_m.group(1).strip())

            if slug_m and title_m:
                items.append({
                    "id": slug_m.group(1).strip(),
                    "title": title_m.group(1).strip(),
                    "description": "",
                    "author": None,
                    "status": "Ongoing",
                    "year": None,
                    "tags": tags,
                    "cover_url": img_m.group(1) if img_m else "",
                })
        if items:
            return items

    # 2. Parse legacy / api.komiku.org bge blocks
    bge_blocks = html.split('<div class="bge">')[1:]
    for block in bge_blocks:
        slug_m = re.search(r'href="https://komiku\.org/manga/([^/]+)/"', block) or re.search(r'href="/manga/([^/]+)/"', block)
        title_m = re.search(r'<h3>\s*(.*?)\s*</h3>', block, re.DOTALL)
        thumb_m = re.search(r'<img[^>]+(?:src|data-src)="([^"]+)"', block)
        type_m = re.search(r'<b>\s*(.*?)\s*</b>', block)
        desc_m = re.search(r'<p>\s*(.*?)\s*</p>', block, re.DOTALL)

        if slug_m and title_m:
            slug = slug_m.group(1).strip()
            title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
            thumb = thumb_m.group(1) if thumb_m else ""
            m_type = type_m.group(1).strip() if type_m else "Manga"
            desc = desc_m.group(1).strip() if desc_m else ""

            items.append({
                "id": slug,
                "title": title,
                "description": desc,
                "author": None,
                "status": "Ongoing",
                "year": None,
                "tags": [m_type],
                "cover_url": thumb,
            })
    return items


_parse_komiku_bge = _parse_komiku_html


# ---------------------------------------------------------------------------
# MangaDex Helpers
# ---------------------------------------------------------------------------

def _first_text(mapping: dict | None, default: str = "") -> str:
    if not isinstance(mapping, dict) or not mapping:
        return default
    return mapping.get("en") or mapping.get("id") or next(iter(mapping.values()), default)


def _parse_manga(m: dict) -> dict:
    manga_id = m.get("id") or ""
    attr = m.get("attributes") or {}
    relationships = m.get("relationships") or []

    cover_url = FALLBACK_COVER
    authors = []
    for rel in relationships:
        rel_type = rel.get("type")
        rel_attr = rel.get("attributes") or {}
        if rel_type == "cover_art" and rel_attr.get("fileName") and cover_url == FALLBACK_COVER:
            cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{rel_attr['fileName']}"
        elif rel_type == "author" and rel_attr.get("name"):
            authors.append(rel_attr["name"])

    tags = [
        name
        for t in attr.get("tags") or []
        if (name := ((t.get("attributes") or {}).get("name") or {}).get("en"))
    ]

    return {
        "id": manga_id,
        "title": _first_text(attr.get("title"), "Unknown Title"),
        "description": _first_text(attr.get("description"), ""),
        "author": ", ".join(authors) if authors else None,
        "status": attr.get("status"),
        "year": attr.get("year"),
        "tags": tags,
        "cover_url": cover_url,
    }


def _search_mangadex(query: str, limit: int = 10):
    data = _fetch_json(
        "/manga",
        params={
            "title": query,
            "limit": limit,
            "includes[]": ["cover_art", "author"],
        },
    )
    results = [_parse_manga(m) for m in data.get("data") or []]
    return {"query": query, "limit": limit, "results": results}


def _get_home_mangadex(limit: int = 10, include_nsfw: bool = False):
    ratings = ["safe", "suggestive"]
    if include_nsfw:
        ratings.extend(["erotica", "pornographic"])

    data = _fetch_json(
        "/manga",
        params={
            "order[followedCount]": "desc",
            "limit": 50,
            "includes[]": ["cover_art", "author"],
            "contentRating[]": ratings,
        },
    )
    results = [_parse_manga(m) for m in data.get("data") or []]
    if len(results) > limit:
        results = random.sample(results, limit)
    return {"results": results}


def _get_chapters_mangadex(manga_id: str, limit: int = 100, offset: int = 0, lang: str = "id,en"):
    langs = [x.strip() for x in lang.split(",") if x.strip()] or ["en"]
    data = _fetch_json(
        f"/manga/{manga_id}/feed",
        params={
            "translatedLanguage[]": langs,
            "limit": limit,
            "offset": offset,
            "order[chapter]": "asc",
        },
    )
    chapters = []
    for c in data.get("data") or []:
        attr = c.get("attributes") or {}
        chapters.append({
            "id": c.get("id"),
            "chapter": attr.get("chapter"),
            "title": attr.get("title"),
            "translatedLanguage": attr.get("translatedLanguage"),
        })
    return {"manga_id": manga_id, "chapters": chapters}


def _get_chapter_pages_mangadex(chapter_id: str):
    data = _fetch_json(f"/at-home/server/{chapter_id}")
    base_url = data.get("baseUrl")
    chapter = data.get("chapter") or {}
    hash_ = chapter.get("hash")
    pages = chapter.get("data") or []
    if not base_url or not hash_:
        raise HTTPException(status_code=502, detail="Incomplete MangaDex at-home response")

    page_urls = [f"{base_url}/data/{hash_}/{p}" for p in pages]
    return {"chapter_id": chapter_id, "pages": page_urls}


# ---------------------------------------------------------------------------
# Public Unified API Methods
# ---------------------------------------------------------------------------

def get_home_manga(limit: int = 10, komik_type: str | None = None, include_nsfw: bool = False):
    urls = []
    if komik_type and komik_type.lower() in ("manhwa", "manhua", "manga"):
        urls.append(f"https://komiku.org/pustaka/?tipe={komik_type.lower()}")
    urls.extend([
        "https://komiku.org/manga/page/1/",
        "https://api.komiku.org/manga/page/1/",
    ])

    for url in urls:
        html = _fetch_komiku(url)
        if html:
            results = _parse_komiku_html(html)
            if results:
                if komik_type and komik_type.lower() != "all":
                    target = komik_type.strip().lower()
                    filtered = [m for m in results if any(t.lower() == target for t in m.get("tags", []))]
                    if filtered:
                        return {"results": filtered[:limit]}
                return {"results": results[:limit]}

    return _get_home_mangadex(limit=limit, include_nsfw=include_nsfw)


def search_manga(query: str, limit: int = 10):
    query = query.strip()
    html = _fetch_komiku("https://api.komiku.org/", params={"post_type": "manga", "s": query})
    if html:
        results = _parse_komiku_bge(html)
        if results:
            return {"query": query, "limit": limit, "results": results[:limit]}

    return _search_mangadex(query, limit)


def get_chapters(manga_id: str, limit: int = 100, offset: int = 0, lang: str = "id,en"):
    manga_id = manga_id.strip()
    if not manga_id:
        raise HTTPException(status_code=400, detail="manga_id is required")

    html = _fetch_komiku(f"https://komiku.org/manga/{manga_id}/")
    if html:
        chap_matches = re.findall(r'<a href="/([^/]+)/"[^>]*title="[^"]*Chapter\s*([^"]+)"', html)
        if not chap_matches:
            chap_slugs = re.findall(r'href="/([^/]+-chapter-[^/]+)/"', html)
            chap_matches = [(cs, cs.split("chapter-")[-1]) for cs in dict.fromkeys(chap_slugs)]

        if chap_matches:
            chapters = []
            for chap_slug, chap_num in chap_matches:
                chapters.append({
                    "id": chap_slug,
                    "chapter": chap_num.strip(),
                    "title": f"Chapter {chap_num.strip()}",
                    "translatedLanguage": "id",
                })
            return {"manga_id": manga_id, "chapters": chapters[offset:offset+limit]}

    return _get_chapters_mangadex(manga_id, limit=limit, offset=offset, lang=lang)


def get_chapter_pages(chapter_id: str):
    chapter_id = chapter_id.strip()
    if not chapter_id:
        raise HTTPException(status_code=400, detail="chapter_id is required")

    for url in [f"https://komiku.org/{chapter_id}/", f"https://komiku.org/ch/{chapter_id}/"]:
        html = _fetch_komiku(url)
        if html:
            baca_m = re.search(r'id="Baca_Komik".*?</section>', html, re.DOTALL) or re.search(r'id="Baca_Komik".*?</div>', html, re.DOTALL)
            target_html = baca_m.group(0) if baca_m else html
            raw_imgs = re.findall(r'<img[^>]+(?:src|data-src)="([^"]+)"', target_html)
            pages = [img for img in raw_imgs if "komiku" in img and ("upload" in img or "img." in img or "chapter" in img)]
            if pages:
                return {"chapter_id": chapter_id, "pages": pages}

    return _get_chapter_pages_mangadex(chapter_id)
