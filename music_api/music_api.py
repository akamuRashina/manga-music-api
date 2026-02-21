from ytmusicapi import YTMusic
import yt_dlp
from fastapi import HTTPException
import random


ytmusic = YTMusic()  # no login required

def search_song_with_recommendation(query: str, limit: int = 10):
    """
    Search lagu berdasarkan query user + rekomendasi terkait query itu.
    """
    search_results = search_song(query, limit)

    # Rekomendasi bisa pakai search tambahan, misal keyword mirip
    # misal ambil 5 lagu rekomendasi
    recommendation_results = search_song(query + " hits", limit=5)

    return {
        "query": query,
        "search_results": search_results.get("results", []),
        "recommended": recommendation_results.get("results", [])
    }

def search_song(query: str, limit: int = 10):
    try:
        results = ytmusic.search(query, filter="songs", limit=limit)
        songs = []
        for r in results:
            songs.append({
                "videoId": r.get("videoId"),
                "title": r.get("title"),
                "artists": [a["name"] for a in r.get("artists", [])],
                "album": r.get("album", {}).get("name"),
                "duration": r.get("duration"),
                "thumbnails": r.get("thumbnails", []),
            })
        return {"query": query, "results": songs}
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "Search failed", "last_error": str(e)})

def get_audio_stream(video_id: str):
    """
    Return direct audio-only URL and necessary headers for a YouTube Music video.
    Uses yt-dlp to extract best audio format URL and headers.
    """
    try:
        ydl_opts = {
            # GANTI: Gunakan format yang mencari audio-only terbaik, lalu coba format m4a (audio umum) jika gagal.
            'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio', 
            'noplaylist': True,
            'quiet': True,
            'extract_flat': True,
            'simulate': True, 
            'skip_download': True,
            # Tambahkan User-Agent yang meniru browser di level yt-dlp, jika ekstrak info gagal tanpa ini.
            'default_search': 'ytsearch', # Opsional, tapi aman
            'force_generic_names': True, # Opsional
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://music.youtube.com/watch?v={video_id}", download=False)
            
            best_audio = None
            
            # 1. Cek apakah yt-dlp sudah memberikan format terbaik secara otomatis
            if info.get('url') and info.get('http_headers'):
                # Ini sering terjadi jika yt-dlp berhasil memilih format terbaik secara internal
                best_audio = info
            else:
                # 2. Iterasi manual untuk mencari audio-only
                for f in info.get('formats', []):
                    # Kriteria: Harus ada codec audio, tidak ada codec video, dan memiliki URL
                    if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('url'):
                        best_audio = f
                        break 
            
            if best_audio:
                stream_url = best_audio.get('url')
                stream_headers = best_audio.get('http_headers', {})
                
                # Jaga-jaga: tambahkan User-Agent jika tidak ada (untuk httpx di main.py)
                if 'User-Agent' not in stream_headers:
                     stream_headers['User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"

                return {
                    "videoId": video_id, 
                    "audio_url": stream_url,
                    "headers": stream_headers
                }
        
        # GANTI error message agar lebih informatif
        raise Exception(f"No audio stream found for ID {video_id} after checking all formats. Available formats: {len(info.get('formats', []))}")
    except Exception as e:
        # Gunakan HTTPException yang sudah diimpor
        raise HTTPException(status_code=502, detail={"error": "Failed to extract stream info (yt-dlp)", "last_error": str(e)})

def get_home_songs(limit: int = 10):
    songs = []
    try:
        try:
            charts = ytmusic.get_charts(country="ID")
            for c in charts:
                if isinstance(c, dict) and c.get("type") == "song":
                    songs.append({
                        "videoId": c.get("videoId"),
                        "title": c.get("title"),
                        "artists": [a["name"] for a in c.get("artists", [])] if c.get("artists") else [],
                        "album": c.get("album", {}).get("name") if isinstance(c.get("album"), dict) else None,
                        "duration": c.get("duration"),
                        "thumbnails": c.get("thumbnails", [])
                    })
        except Exception as chart_error:
            print("⚠️ Chart fetch failed:", chart_error)
        
        if not songs:
            hits = ytmusic.search("hits indonesia", filter="songs", limit=limit)
            for r in hits:
                songs.append({
                    "videoId": r.get("videoId"),
                    "title": r.get("title"),
                    "artists": [a["name"] for a in r.get("artists", [])],
                    "album": r.get("album", {}).get("name"),
                    "duration": r.get("duration"),
                    "thumbnails": r.get("thumbnails", [])
                })
        
        if len(songs) > limit:
            songs = random.sample(songs, limit)

        return {"results": songs}
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "Failed to fetch home songs", "last_error": str(e)})