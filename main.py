from fastapi import FastAPI, Query, HTTPException
from manga_api.manga_api import search_manga, get_chapters, get_chapter_pages, get_home_manga
from music_api.music_api import get_audio_stream, get_home_songs, search_song_with_recommendation  # dari kode music_api.py kamu
from fastapi.responses import RedirectResponse
from fastapi.responses import RedirectResponse, StreamingResponse
import httpx

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"

app = FastAPI(title="Manga + Music API Backend")

@app.get("/")
def root():
    return {"message": "Backend Manga + Music running"}

@app.get("/manga/search")
def manga_search(q: str = Query(...), limit: int = Query(10)):
    return search_manga(q, limit)

@app.get("/manga/{manga_id}/chapters")
def manga_chapters(manga_id: str, limit: int = Query(50)):
    return get_chapters(manga_id, limit)

@app.get("/chapter/{chapter_id}/pages")
def chapter_pages(chapter_id: str):
    return get_chapter_pages(chapter_id)

@app.get("/manga/home")
def manga_home(limit: int = 10):
    return get_home_manga(limit)

@app.get("/music/search")
def music_search(q: str = Query(...)):
    return search_song_with_recommendation(q)

@app.get("/music/{video_id}/stream")
async def music_stream(video_id: str): 

    result = get_audio_stream(video_id) 
    stream_url = result["audio_url"]
    stream_headers = result.get("headers", {})

    async def audio_stream_generator(url: str, headers: dict):

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:

                async with client.stream("GET", url, headers=headers) as r:
                    r.raise_for_status() 
                    
                    content_type = r.headers.get("Content-Type", "audio/webm") 
                    
                    async for chunk in r.aiter_bytes():
                        yield chunk
            except httpx.HTTPStatusError as e:
                 raise HTTPException(status_code=502, detail=f"Failed to stream from source: {e}")
            except Exception as e:
                 raise HTTPException(status_code=502, detail=f"Streaming error: {e}")

    return StreamingResponse(
        audio_stream_generator(stream_url, stream_headers),
        media_type="audio/webm" 
    )

@app.get("/music/home")
def music_home(limit: int = 10):
    return get_home_songs(limit)