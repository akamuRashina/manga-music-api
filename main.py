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


@app.get("/comic/home")
@app.get("/komik/home")
def comic_home(
    limit: int = Query(10, ge=1, le=50),
    type: str | None = Query(None, description="Filter: manga, manhwa, manhua, or all"),
    include_nsfw: bool = Query(False),
):
    return get_home_manga(limit=limit, komik_type=type, include_nsfw=include_nsfw)


@app.get("/manga/home")
def manga_home(
    limit: int = Query(10, ge=1, le=50),
    type: str | None = Query(None, description="Filter: manga, manhwa, manhua"),
    include_nsfw: bool = Query(False),
):
    return get_home_manga(limit=limit, komik_type=type or "manga", include_nsfw=include_nsfw)


@app.get("/manhwa/home")
def manhwa_home(limit: int = Query(10, ge=1, le=50)):
    return get_home_manga(limit=limit, komik_type="manhwa")


@app.get("/manhua/home")
def manhua_home(limit: int = Query(10, ge=1, le=50)):
    return get_home_manga(limit=limit, komik_type="manhua")


@app.get("/comic/search")
@app.get("/komik/search")
@app.get("/manga/search")
def comic_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=100)):
    return search_manga(q, limit)


@app.get("/comic/{comic_id}/chapters")
@app.get("/komik/{comic_id}/chapters")
@app.get("/manga/{manga_id}/chapters")
def comic_chapters(
    comic_id: str | None = None,
    manga_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    lang: str = Query("id,en"),
):
    target_id = comic_id or manga_id or ""
    return get_chapters(target_id, limit=limit, offset=offset, lang=lang)


@app.get("/chapter/{chapter_id}/pages")
def chapter_pages(chapter_id: str):
    return get_chapter_pages(chapter_id)


@app.get("/music/search")
def music_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    return search_song_with_recommendation(q, limit=limit)


@app.get("/music/home")
def music_home(limit: int = Query(10, ge=1, le=50)):
    return get_home_songs(limit=limit)
