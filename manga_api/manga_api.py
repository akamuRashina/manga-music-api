import requests
import random
from fastapi import HTTPException

# Daftar BASE_URLS yang benar, menghapus 'https://mangadex.network'
BASE_URLS = [
    "https://api.mangadex.org",
    "https://api.mangadex.dev",
]

FALLBACK_COVER = "https://mangadex.org/_nuxt/img/cover-placeholder.d12c3c5.jpg"

def safe_cover_url(manga_id: str, relationships: list):
    """Ambil URL cover tanpa pengecekan HEAD agar cepat"""
    for rel in relationships:
        if rel.get("type") == "cover_art":
            filename = rel.get("attributes", {}).get("fileName")
            if filename:
                # ✅ Gunakan format URL cover asli dari Mangadex
                # Contoh hasil: https://uploads.mangadex.org/covers/37f5cce0.../6bfc8f2a....jpg
                return f"https://uploads.mangadex.org/covers/{manga_id}/{filename}"
    # fallback kalau gak ada cover
    return FALLBACK_COVER


def search_manga(query: str, limit: int = 10):
    last_error = None
    for base in BASE_URLS:
        try:
            # Menggunakan endpoint /manga
            r = requests.get(f"{base}/manga", params={"title": query, "limit": limit, "includes[]": "cover_art"}, timeout=10)
            r.raise_for_status()
            data = r.json()
            results = []
            for m in data.get("data", []):
                attr = m["attributes"]
                relationships = m.get("relationships", [])

                cover_url = safe_cover_url(m["id"], relationships)

                # Logika title yang lebih aman jika 'en' tidak ada
                title = attr["title"].get("en") or next(iter(attr["title"].values()), "No Title")
                desc = attr.get("description", {}).get("en", "")
                tags = [t["attributes"]["name"]["en"] for t in attr.get("tags", []) if "en" in t["attributes"]["name"]]
                results.append({
                    "id": m["id"],
                    "title": title,
                    "description": desc,
                    "status": attr.get("status"),
                    "year": attr.get("year"),
                    "tags": tags,
                    "cover_url": cover_url
                })
            return {"query": query, "limit": limit, "results": results}
        except Exception as e:
            last_error = str(e)
            continue
    raise HTTPException(status_code=502, detail={"error": "All sources failed", "last_error": last_error})


def get_home_manga(limit: int = 10):
    last_error = None
    for base in BASE_URLS:
        try:
            url = f"{base}/manga"
            params = {
                "order[followedCount]": "desc",
                "limit": 50,
                "includes[]": "cover_art",
                # Parameter array contentRating[] dikirim sebagai list, requests akan menanganinya
                "contentRating[]": ["safe", "suggestive", "erotica", "pornographic"], 
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            mangas = data.get("data", [])

            results = []
            for m in mangas:
                attributes = m.get("attributes", {})
                relationships = m.get("relationships", [])
                cover_url = safe_cover_url(m["id"], relationships)
                
                # Logika title yang lebih aman jika 'en' tidak ada
                title = attributes.get("title", {}).get("en") or next(iter(attributes.get("title", {}).values()), "Unknown")
                
                tags = []
                for t in attributes.get("tags", []):
                    tag_name = t.get("attributes", {}).get("name", {}).get("en")
                    if tag_name:
                        tags.append(tag_name)

                results.append({
                    "id": m.get("id"),
                    "title": title,
                    "description": attributes.get("description", {}).get("en", ""),
                    "status": attributes.get("status"),
                    "year": attributes.get("year"),
                    "tags": tags,
                    "cover_url": cover_url
                })

            if len(results) > limit:
                results = random.sample(results, limit)

            return {"results": results}

        except Exception as e:
            last_error = str(e)
            continue

    raise HTTPException(status_code=502, detail={"error": "Failed to fetch home manga", "last_error": last_error})


def get_chapters(manga_id: str, limit: int = 50):
    last_error = None
    params = {"translatedLanguage[]": "en", "limit": limit, "order[chapter]": "asc"}
    for base in BASE_URLS:
        try:
            # Menggunakan endpoint /manga/{id}/feed
            r = requests.get(f"{base}/manga/{manga_id}/feed", params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            chapters = []
            for c in data.get("data", []):
                attr = c.get("attributes", {})
                chapters.append({
                    "id": c.get("id"),
                    "chapter": attr.get("chapter"),
                    "title": attr.get("title"),
                    "translatedLanguage": attr.get("translatedLanguage"),
                })
            return {"manga_id": manga_id, "chapters": chapters}
        except Exception as e:
            last_error = str(e)
            continue
    raise HTTPException(status_code=502, detail={"error": "Failed to fetch chapters", "last_error": last_error})


def get_chapter_pages(chapter_id: str):
    last_error = None
    for base in BASE_URLS:
        try:
            # Menggunakan endpoint /at-home/server/{chapter_id}
            r = requests.get(f"{base}/at-home/server/{chapter_id}", timeout=10)
            r.raise_for_status()
            data = r.json()
            base_url = data.get("baseUrl")
            chapter = data.get("chapter", {})
            hash_ = chapter.get("hash")
            pages = chapter.get("data", [])
            page_urls = [f"{base_url}/data/{hash_}/{p}" for p in pages]
            return {"chapter_id": chapter_id, "pages": page_urls}
        except Exception as e:
            last_error = str(e)
            continue
    raise HTTPException(status_code=502, detail={"error": "Failed to fetch chapter pages", "last_error": last_error})