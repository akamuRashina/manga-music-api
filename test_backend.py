import unittest
from unittest.mock import patch

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

    def test_manga_chapters_defaults_to_id_and_en(self):
        fake_feed = {
            "data": [
                {"id": "c1", "attributes": {"chapter": "1", "title": "Bab 1", "translatedLanguage": "id"}}
            ]
        }
        with patch.object(manga_api, "_fetch_json", return_value=fake_feed) as mock_fetch:
            res = self.client.get("/manga/m1/chapters?offset=50")
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

    def test_music_search_deduplicates_recommendations(self):
        main_hits = [{"videoId": "v1", "title": "Main", "artists": [{"name": "A"}]}]
        rec_hits = [
            {"videoId": "v1", "title": "Main", "artists": [{"name": "A"}]},
            {"videoId": "v2", "title": "Rec", "artists": [{"name": "B"}]},
        ]
        with patch.object(music_api.ytmusic, "search", side_effect=[main_hits, rec_hits]):
            res = self.client.get("/music/search?q=test")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual([s["videoId"] for s in body["search_results"]], ["v1"])
        self.assertEqual([s["videoId"] for s in body["recommended"]], ["v2"])


if __name__ == "__main__":
    unittest.main()
