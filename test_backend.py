import base64
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import main
from manga_api import manga_api
from music_api import music_api


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_manga_home_defaults_safe_and_parses_author(self):
        fake_payload = {
            "data": [
                {
                    "id": "m1",
                    "attributes": {
                        "title": {"ja-ro": "Judul"},
                        "description": {"id": "Deskripsi ID"},
                        "status": "ongoing",
                        "year": 2024,
                        "tags": [{"attributes": {"name": {"en": "Action"}}}],
                    },
                    "relationships": [
                        {"type": "cover_art", "attributes": {"fileName": "c.jpg"}},
                        {"type": "author", "attributes": {"name": "Author A"}},
                    ],
                }
            ]
        }
        with patch.object(manga_api, "_fetch_json", return_value=fake_payload) as mock_fetch:
            res = self.client.get("/manga/home")
        self.assertEqual(res.status_code, 200)
        item = res.json()["results"][0]
        self.assertEqual(item["author"], "Author A")
        self.assertEqual(item["cover_url"], "https://uploads.mangadex.org/covers/m1/c.jpg")
        params = mock_fetch.call_args.kwargs["params"]
        self.assertEqual(params["contentRating[]"], ["safe", "suggestive"])

    def test_manga_chapters_supports_id_lang(self):
        fake_feed = {
            "data": [
                {"id": "c1", "attributes": {"chapter": "1", "title": "Bab 1", "translatedLanguage": "id"}}
            ]
        }
        with patch.object(manga_api, "_fetch_json", return_value=fake_feed) as mock_fetch:
            res = self.client.get("/manga/m1/chapters?lang=id,en&offset=50")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["chapters"][0]["translatedLanguage"], "id")
        params = mock_fetch.call_args.kwargs["params"]
        self.assertEqual(params["translatedLanguage[]"], ["id", "en"])
        self.assertEqual(params["offset"], 50)

    def test_chapter_pages_rejects_incomplete_response(self):
        with patch.object(manga_api, "_fetch_json", return_value={"baseUrl": None, "chapter": {}}):
            res = self.client.get("/chapter/c1/pages")
        self.assertEqual(res.status_code, 502)

    def test_music_home_parses_chart_playlist_and_none_album(self):
        charts_resp = {"videos": [{"title": "Top ID", "playlistId": "PL123"}]}
        playlist_resp = {
            "tracks": [
                {
                    "videoId": "v1",
                    "title": "Lagu",
                    "artists": [{"name": "Artis"}],
                    "album": None,
                    "duration": "3:00",
                    "thumbnails": [],
                }
            ]
        }
        with patch.object(music_api.ytmusic, "get_charts", return_value=charts_resp), \
             patch.object(music_api.ytmusic, "get_playlist", return_value=playlist_resp):
            res = self.client.get("/music/home")
        self.assertEqual(res.status_code, 200)
        song = res.json()["results"][0]
        self.assertEqual(song["videoId"], "v1")
        self.assertIsNone(song["album"])

    def test_music_stream_forwards_media_type_range_and_502_before_stream(self):
        fake_stream = {"videoId": "v1", "audio_url": "https://cdn.example/audio", "headers": {}}

        async def ok_send(req, stream=True):
            resp = MagicMock()
            resp.status_code = 206
            resp.headers = {"Content-Type": "audio/mp4", "Content-Range": "bytes 0-3/10", "Content-Length": "4"}
            resp.raise_for_status = MagicMock()

            async def aiter_bytes():
                yield b"abcd"

            async def aclose():
                return None

            resp.aiter_bytes = aiter_bytes
            resp.aclose = aclose
            return resp

        with patch.object(main, "get_audio_stream", return_value=fake_stream), \
             patch("httpx.AsyncClient.send", side_effect=ok_send):
            res = self.client.get("/music/v1/stream", headers={"Range": "bytes=0-3"})
        self.assertEqual(res.status_code, 206)
        self.assertEqual(res.headers["content-type"], "audio/mp4")
        self.assertEqual(res.headers["content-range"], "bytes 0-3/10")
        self.assertEqual(res.content, b"abcd")

        with patch.object(main, "get_audio_stream", return_value=fake_stream), \
             patch("httpx.AsyncClient.send", side_effect=main.httpx.ConnectError("boom")):
            err = self.client.get("/music/v1/stream")
        self.assertEqual(err.status_code, 502)

    def test_cookies_base64_writes_to_tempdir(self):
        encoded = base64.b64encode(b"# Netscape HTTP Cookie File\n").decode("ascii")
        with patch.dict(os.environ, {"COOKIES_BASE64": encoded}):
            path = music_api._get_cookie_file()
        self.assertIsNotNone(path)
        self.assertTrue(os.path.isfile(path))
        self.assertNotEqual(os.path.dirname(path), music_api.BASE_DIR)


if __name__ == "__main__":
    unittest.main()
