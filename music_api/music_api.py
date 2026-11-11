import logging
import random

from fastapi import HTTPException
from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)
ytmusic = YTMusic()


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
