import random
import requests
from fastapi import HTTPException

BASE_URLS = [
    "https://api.mangadex.org",
    "https://api.mangadex.dev",
]
FALLBACK_COVER = "https://mangadex.org/_nuxt/img/cover-placeholder.d12c3c5.jpg"
_session = requests.Session()


def _fetch_json(path: str, params: dict | list | None = None) -> dict:
    last_error = None
    for base in BASE_URLS:
        try:
            r = _session.get(f"{base}{path}", params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_error = str(e)
    raise HTTPException(status_code=502, detail={"error": "All MangaDex sources failed", "last_error": last_error})


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


def search_manga(query: str, limit: int = 10):
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


def get_home_manga(limit: int = 10, include_nsfw: bool = False):
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


def get_chapters(manga_id: str, limit: int = 100, offset: int = 0, lang: str = "en"):
    manga_id = manga_id.strip()
    if not manga_id:
        raise HTTPException(status_code=400, detail="manga_id is required")

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


def get_chapter_pages(chapter_id: str):
    chapter_id = chapter_id.strip()
    if not chapter_id:
        raise HTTPException(status_code=400, detail="chapter_id is required")

    data = _fetch_json(f"/at-home/server/{chapter_id}")
    base_url = data.get("baseUrl")
    chapter = data.get("chapter") or {}
    hash_ = chapter.get("hash")
    pages = chapter.get("data") or []
    if not base_url or not hash_:
        raise HTTPException(status_code=502, detail="Incomplete MangaDex at-home response")

    page_urls = [f"{base_url}/data/{hash_}/{p}" for p in pages]
    return {"chapter_id": chapter_id, "pages": page_urls}
