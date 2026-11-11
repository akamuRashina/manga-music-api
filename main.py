from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from manga_api.manga_api import get_chapter_pages, get_chapters, get_home_manga, search_manga
from music_api.music_api import get_home_songs, search_song_with_recommendation

app = FastAPI(title="Manga + Music API Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Backend Manga + Music running"}


@app.get("/manga/search")
def manga_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=100)):
    return search_manga(q, limit)


@app.get("/manga/{manga_id}/chapters")
def manga_chapters(
    manga_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    lang: str = Query("id,en"),
):
    return get_chapters(manga_id, limit=limit, offset=offset, lang=lang)


@app.get("/chapter/{chapter_id}/pages")
def chapter_pages(chapter_id: str):
    return get_chapter_pages(chapter_id)


@app.get("/manga/home")
def manga_home(limit: int = Query(10, ge=1, le=50), include_nsfw: bool = Query(False)):
    return get_home_manga(limit=limit, include_nsfw=include_nsfw)


@app.get("/music/search")
def music_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    return search_song_with_recommendation(q, limit=limit)


@app.get("/music/home")
def music_home(limit: int = Query(10, ge=1, le=50)):
    return get_home_songs(limit=limit)
