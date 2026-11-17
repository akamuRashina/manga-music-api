import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from manga_api import manga_api
from music_api import music_api


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_manga_home_parses_komiku(self):
        sample_html = '''
        <div class="bge">
            <div class="bgei">
                <a href="https://komiku.org/manga/test-manga/">
                    <img src="https://img.test/c.jpg" class="sd">
                    <div class="tpe1_inf"><b>Manhwa</b> Aksi</div>
                </a>
            </div>
            <div class="kan">
                <a href="https://komiku.org/manga/test-manga/"><h3>Test Manga</h3></a>
                <p>Sinopsis manga test</p>
            </div>
        </div>
        '''
        with patch.object(manga_api, "_fetch_komiku", return_value=sample_html):
            res = self.client.get("/manga/home")
        self.assertEqual(res.status_code, 200)
        results = res.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "test-manga")
        self.assertEqual(results[0]["title"], "Test Manga")
        self.assertEqual(results[0]["cover_url"], "https://img.test/c.jpg")
        self.assertEqual(results[0]["tags"], ["Manhwa"])

    def test_manga_home_falls_back_to_mangadex(self):
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
        with patch.object(manga_api, "_fetch_komiku", return_value=None), \
             patch.object(manga_api, "_fetch_json", return_value=fake_payload) as mock_fetch:
            res = self.client.get("/manga/home")
        self.assertEqual(res.status_code, 200)
        item = res.json()["results"][0]
        self.assertEqual(item["author"], "Author A")
        self.assertEqual(item["cover_url"], "https://uploads.mangadex.org/covers/m1/c.jpg")
        params = mock_fetch.call_args.kwargs["params"]
        self.assertEqual(params["contentRating[]"], ["safe", "suggestive"])

    def test_manga_chapters_komiku_and_fallback(self):
        sample_detail = '''
        <div id="Daftar_Chapter">
            <a href="/test-manga-chapter-01/" title="Baca Chapter 01">Chapter 01</a>
            <a href="/test-manga-chapter-02/" title="Baca Chapter 02">Chapter 02</a>
        </div>
        '''
        with patch.object(manga_api, "_fetch_komiku", return_value=sample_detail):
            res = self.client.get("/manga/test-manga/chapters")
        self.assertEqual(res.status_code, 200)
        chaps = res.json()["chapters"]
        self.assertEqual(len(chaps), 2)
        self.assertEqual(chaps[0]["id"], "test-manga-chapter-01")
        self.assertEqual(chaps[0]["translatedLanguage"], "id")

    def test_chapter_pages_komiku(self):
        sample_page = '''
        <section id="Baca_Komik">
            <img src="https://img.komiku.org/upload/1.webp">
            <img src="https://img.komiku.org/upload/2.webp">
        </section>
        '''
        with patch.object(manga_api, "_fetch_komiku", return_value=sample_page):
            res = self.client.get("/chapter/test-manga-chapter-01/pages")
        self.assertEqual(res.status_code, 200)
        pages = res.json()["pages"]
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0], "https://img.komiku.org/upload/1.webp")

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
