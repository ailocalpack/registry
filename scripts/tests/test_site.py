"""Tests of scripts/site.py (the registry's public site) and scripts/games-md.py.

    python3 -I scripts/tests/test_site.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("site_script", os.path.join(SCRIPTS, "site.py"))
site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(site)


def pack(game_folder, lang, pack_id, status="alpha", likes=0, works=0, broken=0, title="Translation", **extra):
    entry = {
        "id": pack_id, "title": title, "author": {"github": "alice"}, "status": status, "revision": 2,
        "updated": "2026-11-10T10:00:00Z", "coverage": {"translated": 90, "total": 100}, "buildIds": ["123"],
        "buildCount": 1, "manifest": f"games/{game_folder}/{lang}/{pack_id}/manifest.json", "size": 10,
        "rating": {"likes": likes, "works": works, "doesNotWork": broken},
        "discussion": "https://github.com/ailocalpack/registry/discussions/7",
    }
    entry.update(extra)
    return entry


INDEX = {
    "schemaVersion": 1,
    "generated": "2026-11-19T12:00:00Z",
    "games": {
        "steam:620": {
            "packs": {
                "ru": [pack("steam-620", "ru", "full", "verified", likes=12, works=5, broken=1)],
                "de": [pack("steam-620", "de", "komplett", likes=2)],
            },
            "requests": {"tr": {"votes": 7, "discussion": "https://github.com/ailocalpack/registry/discussions/9",
                                "opened": "2026-11-01T00:00:00Z"}},
        },
        "steam:700": {
            "packs": {"uk": [pack("steam-700", "uk", "x", title='<script>alert("x")</script>')]},
        },
        "steam:800": {
            "requests": {"ru": {"votes": 31, "discussion": "https://github.com/ailocalpack/registry/discussions/11",
                                "opened": "2026-11-02T00:00:00Z",
                                "claim": {"by": "lampwright", "state": "working", "stage": "translate",
                                          "percent": 62, "updated": "2026-11-18T00:00:00Z"}}},
        },
        "steam:400": {"optOut": True, "packs": {"ru": [pack("steam-400", "ru", "nope")]}},
        "steam:500": {"antiCheat": "eac", "requests": {"ru": {"votes": 3, "discussion": "https://x/1",
                                                              "opened": "2026-11-02T00:00:00Z"}}},
        "steam:570": {"antiCheat": "vac", "antiCheatAllowed": True,
                      "packs": {"fr": [pack("steam-570", "fr", "complet")]}},
        "steam:900": {},
    },
}

NAMES = {
    "steam:620": {"name": "Portal 2", "image": "https://cdn.example/620.jpg"},
    "steam:700": {"name": "Tom & Jerry <Deluxe>", "image": ""},
    "steam:800": {"name": "OMORI", "image": "https://cdn.example/800.jpg"},
    "steam:570": {"name": "Dota 2", "image": ""},
}


def manifest(lang, pack_id, recipe=None, game_name=None, updated="2026-11-10T10:00:00Z"):
    m = {"id": pack_id, "updated": updated, "language": lang, "title": "T", "authors": [{"github": "alice", "name": "Alice"}],
         "agent": {"id": "claude-code", "quality": "balanced"}, "builds": [{"buildId": "123", "os": "windows"}]}
    if recipe:
        m["recipe"] = {"tool": recipe, "version": "1.0.0"}
    else:
        m["patch"] = {"format": "vcdiff"}
    if game_name:
        m["gameName"] = game_name
    return m


class SiteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "registry")
        self.out = os.path.join(self.tmp, "_site")
        for folder in ("site", "assets"):
            shutil.copytree(os.path.join(REGISTRY, folder), os.path.join(self.root, folder))
        manifests = {("steam-620", "ru", "full"): "unity", ("steam-620", "de", "komplett"): "unity",
                     ("steam-700", "uk", "x"): None, ("steam-570", "fr", "complet"): "godot"}
        for (folder, lang, pack_id), recipe in manifests.items():
            path = os.path.join(self.root, "games", folder, lang, pack_id)
            os.makedirs(path)
            with open(os.path.join(path, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest(lang, pack_id, recipe), f)
        self.fetched = []
        self.answers = {}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def fetch(self, game_id):
        self.fetched.append(game_id)
        return self.answers.get(game_id)

    def add_game(self, game_id, *manifests):
        """A game whose packs are the given (language, pack ID, manifest) triples; returns the index with it."""
        folder = game_id.replace(":", "-")
        packs = {}
        for lang, pack_id, m in manifests:
            path = os.path.join(self.root, "games", folder, lang, pack_id)
            os.makedirs(path)
            with open(os.path.join(path, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(m, f)
            packs.setdefault(lang, []).append(pack(folder, lang, pack_id))
        return {**INDEX, "games": {**INDEX["games"], game_id: {"packs": packs}}}

    def build(self, index=INDEX, names=NAMES):
        return site.build(index, self.root, self.out, "ailocalpack/registry", names, self.fetch)

    def read(self, *path):
        with open(os.path.join(self.out, *path), encoding="utf-8") as f:
            return f.read()

    def test_writes_the_home_page_requests_page_and_one_page_per_shown_game(self):
        # Arrange
        expected = ["games/steam-570/index.html", "games/steam-620/index.html", "games/steam-700/index.html",
                    "games/steam-800/index.html", "index.html", "requests/index.html"]

        # Act
        self.build()

        # Assert
        pages = sorted(os.path.relpath(os.path.join(d, f), self.out).replace(os.sep, "/")
                       for d, _, files in os.walk(self.out) for f in files if f == "index.html")
        self.assertEqual(pages, expected)

    def test_leaves_out_opted_out_games_and_games_blocked_by_anti_cheat(self):
        # Arrange / Act
        self.build()

        # Assert
        home, sitemap = self.read("index.html"), self.read("sitemap.xml")
        for blocked in ("steam-400", "steam-500"):
            self.assertNotIn(blocked, home)
            self.assertNotIn(blocked, sitemap)
            self.assertFalse(os.path.exists(os.path.join(self.out, "games", blocked)))

    def test_escapes_names_and_titles_from_the_index(self):
        # Arrange / Act
        self.build()

        # Assert
        self.assertNotIn("<script>alert", self.read("games", "steam-700", "index.html"))
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", self.read("games", "steam-700", "index.html"))
        self.assertIn("Tom &amp; Jerry &lt;Deluxe&gt;", self.read("index.html"))

    def test_card_data_gives_status_likes_and_works_per_language_and_votes(self):
        # Arrange
        stats = site.attr_json({"de": ["alpha", 2, 0], "ru": ["verified", 12, 5]})
        votes = site.attr_json({"tr": 7})

        # Act
        self.build()

        # Assert
        home = self.read("index.html")
        self.assertIn(f'data-stats="{stats}"', home)
        self.assertIn(f'data-votes="{votes}"', home)

    def test_engine_comes_from_the_recipe_and_a_patch_pack_is_another_engine(self):
        # Arrange / Act
        self.build()

        # Assert
        home = self.read("index.html")
        self.assertIn('data-engine="unity"', home)
        self.assertIn('data-engine="other"', home)
        self.assertIn('data-count-engine="godot"', home)

    def test_a_requested_game_without_packs_gets_a_page_and_a_claimed_request_row(self):
        # Arrange / Act
        self.build()

        # Assert
        requests = self.read("requests", "index.html")
        self.assertIn("OMORI", requests)
        self.assertIn("@lampwright is on it · translating · 62%", requests)
        self.assertIn("translation requested", self.read("games", "steam-800", "index.html"))

    def test_the_game_page_lists_each_pack_with_build_os_agent_and_reviews(self):
        # Arrange / Act
        self.build()

        # Assert
        page = self.read("games", "steam-620", "index.html")
        self.assertIn("Build 123 · Windows", page)
        self.assertIn("Claude Code · Balanced", page)
        self.assertIn("5 works · 1 doesn't", page)
        self.assertIn("https://github.com/ailocalpack/registry/tree/master/games/steam-620/ru/full", page)
        self.assertIn('<meta property="og:image" content="https://cdn.example/620.jpg">', page)

    def test_asks_the_store_only_for_games_with_no_known_name(self):
        # Arrange
        names = {k: v for k, v in NAMES.items() if k != "steam:800"}

        # Act
        self.build(names=names)

        # Assert
        self.assertEqual(self.fetched, ["steam:800"])
        self.assertIn("Steam game 800", self.read("requests", "index.html"))

    def test_an_epic_game_takes_the_newest_manifests_name_and_has_no_store_link(self):
        # Arrange
        index = self.add_game("epic:Fennel", ("ru", "a", manifest("ru", "a", "unity", "Hollow Fields")),
                              ("de", "b", manifest("de", "b", "unity", "Hollow Fields: Remastered", "2026-11-12T00:00:00Z")))

        # Act
        self.build(index)

        # Assert
        page = self.read("games", "epic-Fennel", "index.html")
        self.assertIn("<h1>Hollow Fields: Remastered</h1>", page)
        self.assertIn("your Epic Games library", page)
        self.assertNotIn("Store page", page)

    def test_a_gog_game_takes_the_stores_name_picture_and_page(self):
        # Arrange
        index = self.add_game("gog:1207658924", ("ru", "a", manifest("ru", "a", "unity", "The Witcher")))
        self.answers["gog:1207658924"] = {"name": "The Witcher: Enhanced Edition", "image": "https://cdn.example/w.jpg",
                                          "store": "https://www.gog.com/game/the_witcher"}

        # Act
        self.build(index)

        # Assert
        page = self.read("games", "gog-1207658924", "index.html")
        self.assertIn("<h1>The Witcher: Enhanced Edition</h1>", page)
        self.assertIn('href="https://www.gog.com/game/the_witcher"', page)
        self.assertIn("#b-gog", page)

    def test_a_store_without_an_answer_falls_back_to_the_manifests_name(self):
        # Arrange
        index = self.add_game("gog:42", ("ru", "a", manifest("ru", "a", "unity", "Little Lantern")))

        # Act
        self.build(index)

        # Assert
        page = self.read("games", "gog-42", "index.html")
        self.assertIn("<h1>Little Lantern</h1>", page)
        self.assertNotIn("Store page", page)

    def test_a_manual_game_takes_its_manifests_name_and_is_added_by_folder(self):
        # Arrange
        game_id = "fp:" + "b" * 64
        index = self.add_game(game_id, ("ru", "a", manifest("ru", "a", "unity", "Sample Quest")))

        # Act
        self.build(index)

        # Assert
        page = self.read("games", "fp-" + "b" * 64, "index.html")
        self.assertIn("<h1>Sample Quest</h1>", page)
        self.assertIn("Add game folder", page)
        self.assertEqual([g for g in self.fetched if g.startswith("fp:")], [])

    def test_download_buttons_open_a_menu_with_each_platforms_file_of_the_latest_release(self):
        # Arrange
        latest = "https://github.com/ailocalpack/ailocalpack/releases/latest/download/AiLocalPack-"

        # Act
        self.build()

        # Assert
        page = self.read("games", "steam-620", "index.html")
        self.assertNotIn('class="btn accent" href="https://github.com/ailocalpack/ailocalpack/releases/latest"', page)
        self.assertIn('<details class="dl end"><summary class="btn accent sm">', page)
        for file in ["win-x64-Setup.exe", "win-x64-Portable.zip", "win-arm64-Setup.exe", "win-arm64-Portable.zip",
                     "osx-arm64-Setup.pkg", "osx-arm64-Portable.zip", "osx-x64-Setup.pkg", "osx-x64-Portable.zip",
                     "linux-x64.AppImage"]:
            self.assertIn(f'href="{latest}{file}"', page)

    def test_sitemap_and_robots_name_the_pages_address(self):
        # Arrange / Act
        self.build()

        # Assert
        self.assertIn("<loc>https://ailocalpack.github.io/registry/games/steam-620/</loc>", self.read("sitemap.xml"))
        self.assertIn("Sitemap: https://ailocalpack.github.io/registry/sitemap.xml", self.read("robots.txt"))

    def test_copies_the_stylesheet_script_and_icon(self):
        # Arrange / Act
        self.build()

        # Assert
        for name in ("site.css", "site.js", "icon.svg"):
            self.assertTrue(os.path.isfile(os.path.join(self.out, "assets", name)), name)

    def test_the_same_index_gives_the_same_files(self):
        # Arrange
        self.build()
        first = self.read("index.html") + self.read("games", "steam-620", "index.html")

        # Act
        shutil.rmtree(self.out)
        self.build()

        # Assert
        self.assertEqual(self.read("index.html") + self.read("games", "steam-620", "index.html"), first)

    def test_an_index_without_requests_has_an_empty_requests_page(self):
        # Arrange
        index = {"games": {"steam:620": {"packs": INDEX["games"]["steam:620"]["packs"]}}}

        # Act
        self.build(index=index)

        # Assert
        self.assertIn("No open requests", self.read("requests", "index.html"))
        self.assertNotIn('id="wanted"', self.read("index.html"))


class GamesMdTest(unittest.TestCase):
    def test_writes_the_games_list_with_known_names(self):
        # Arrange
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        index_path, out = os.path.join(tmp, "index.json"), os.path.join(tmp, "GAMES.md")
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump({"games": {"fp:" + "a" * 64: {"packs": {"ru": [pack("fp-" + "a" * 64, "ru", "p")]}}}}, f)

        # Act
        result = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "games-md.py"), index_path,
                                 "--root", tmp, "--out", out], capture_output=True, text=True)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(out, encoding="utf-8") as f:
            self.assertIn("A game added from a folder", f.read())

    def test_names_an_epic_game_by_its_manifest(self):
        # Arrange
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        index_path, out = os.path.join(tmp, "index.json"), os.path.join(tmp, "GAMES.md")
        folder = os.path.join(tmp, "games", "epic-Fennel", "ru", "p")
        os.makedirs(folder)
        with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest("ru", "p", "unity", "Hollow Fields"), f)
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump({"games": {"epic:Fennel": {"packs": {"ru": [pack("epic-Fennel", "ru", "p")]}}}}, f)

        # Act
        result = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "games-md.py"), index_path,
                                 "--root", tmp, "--out", out], capture_output=True, text=True)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(out, encoding="utf-8") as f:
            self.assertIn("**Hollow Fields**", f.read())


if __name__ == "__main__":
    unittest.main()
