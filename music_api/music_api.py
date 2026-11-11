import base64
import logging
import os
import random
import shutil
import sys
import tempfile

from fastapi import HTTPException
import yt_dlp
from yt_dlp.plugins import directories as ytdlp_plugin_dirs
from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"

ytmusic = YTMusic()


def _ensure_bgutil_plugin() -> None:
    """Load local bgutil-ytdlp-pot-provider submodule if not installed via pip."""
    plugin_dir = os.path.join(BASE_DIR, "bgutil-ytdlp-pot-provider", "plugin")
    if not ytdlp_plugin_dirs() and os.path.isdir(plugin_dir) and plugin_dir not in sys.path:
        sys.path.append(plugin_dir)


def _get_cookie_file() -> str | None:
    cookies_b64 = os.environ.get("COOKIES_BASE64")
    if cookies_b64:
        try:
            # Vercel root is read-only; write decoded cookies to system temp dir.
            temp_cookie = os.path.join(tempfile.gettempdir(), "yt_cookies.txt")
            content = base64.b64decode(cookies_b64).decode("utf-8")
            with open(temp_cookie, "w", encoding="utf-8") as f:
                f.write(content)
            return temp_cookie
        except Exception as e:
            logger.warning("Failed to decode COOKIES_BASE64: %s", e)

    local_cookie = os.path.join(BASE_DIR, "cookies.txt")
    return local_cookie if os.path.isfile(local_cookie) else None


def _format_song(r: dict) -> dict:
    album = r.get("album")
    return {
        "videoId": r.get("videoId"),
        "title": r.get("title"),
        "artists": [a["name"] for a in (r.get("artists") or []) if isinstance(a, dict) and a.get("name")],
        "album": album.get("name") if isinstance(album, dict) else None,
        "duration": r.get("duration"),
        "thumbnails": r.get("thumbnails") or [],
    }


def search_song(query: str, limit: int = 10):
    try:
        results = ytmusic.search(query, filter="songs", limit=limit)
        songs = [_format_song(r) for r in results if r.get("videoId")]
        return {"query": query, "results": songs}
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "Search failed", "last_error": str(e)})


def search_song_with_recommendation(query: str, limit: int = 10):
    search_results = search_song(query, limit).get("results", [])
    seen_ids = {s["videoId"] for s in search_results}

    try:
        rec_raw = search_song(f"{query} hits", limit=8).get("results", [])
        recommended = [s for s in rec_raw if s["videoId"] not in seen_ids][:5]
    except HTTPException:
        recommended = []

    return {
        "query": query,
        "search_results": search_results,
        "recommended": recommended,
    }


def get_audio_stream(video_id: str):
    """Return direct audio-only URL using yt-dlp and bgutil POT provider when available."""
    video_id = video_id.strip()
    if not video_id:
        raise HTTPException(status_code=400, detail="video_id is required")

    try:
        _ensure_bgutil_plugin()
        script_path = os.path.join(BASE_DIR, "bgutil-ytdlp-pot-provider", "server", "build", "generate_once.js")
        cookie_file = _get_cookie_file()

        ydl_opts = {
            "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "http_headers": {"User-Agent": DEFAULT_UA},
        }
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file

        if os.path.isfile(script_path) and shutil.which("node"):
            ydl_opts["extractor_args"] = {
                "youtubepot-bgutilscript": {"script_path": [script_path]}
            }
            os.environ.setdefault("TOKEN_TTL", "6")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://music.youtube.com/watch?v={video_id}", download=False) or {}

        best_audio = None
        if info.get("url"):
            best_audio = info
        else:
            # yt-dlp orders formats worst -> best; scan in reverse and prefer direct HTTPS streams.
            audio_formats = [
                f for f in (info.get("formats") or [])
                if f.get("acodec") != "none" and f.get("vcodec") == "none" and f.get("url")
            ]
            direct = [f for f in audio_formats if "m3u8" not in (f.get("protocol") or "")]
            pool = direct or audio_formats
            if pool:
                best_audio = pool[-1]

        if not best_audio:
            raise RuntimeError(f"No audio stream found for ID {video_id}")

        stream_headers = dict(best_audio.get("http_headers") or {})
        stream_headers.setdefault("User-Agent", DEFAULT_UA)
        return {
            "videoId": video_id,
            "audio_url": best_audio["url"],
            "headers": stream_headers,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "Failed to extract stream info (yt-dlp)", "last_error": str(e)})


def get_home_songs(limit: int = 10):
    songs = []
    try:
        try:
            charts = ytmusic.get_charts(country="ID")
            playlists = (
                charts.get("videos")
                or charts.get("daily")
                or charts.get("weekly")
                or []
            )
            playlist_id = playlists[0].get("playlistId") if playlists and isinstance(playlists[0], dict) else None
            if playlist_id:
                playlist = ytmusic.get_playlist(playlist_id, limit=max(limit * 2, 20))
                songs = [_format_song(t) for t in (playlist.get("tracks") or []) if t.get("videoId")]
        except Exception as chart_error:
            logger.warning("Chart fetch failed: %s", chart_error)

        if not songs:
            hits = ytmusic.search("hits indonesia", filter="songs", limit=max(limit * 2, 20))
            songs = [_format_song(r) for r in hits if r.get("videoId")]

        if len(songs) > limit:
            songs = random.sample(songs, limit)

        return {"results": songs}
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "Failed to fetch home songs", "last_error": str(e)})
