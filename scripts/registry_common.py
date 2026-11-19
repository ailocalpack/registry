"""What GAMES.md (scripts/games-md.py) and the site (scripts/site.py) share: language names, Steam names and
header pictures, manifests. Standard library only; the scripts run with `python3 -I` (they add this folder to
sys.path themselves)."""

import json
import os
import re
import urllib.request

# Tag → (English name, native name): the languages Steam supports (the app's GameLanguages.Tags).
LANGUAGES = {
    "ar": ("Arabic", "العربية"), "bg": ("Bulgarian", "Български"), "cs": ("Czech", "Čeština"),
    "da": ("Danish", "Dansk"), "de": ("German", "Deutsch"), "el": ("Greek", "Ελληνικά"),
    "en": ("English", "English"), "es-ES": ("Spanish (Spain)", "Español"),
    "es-419": ("Spanish (Latin America)", "Español (Latinoamérica)"), "fi": ("Finnish", "Suomi"),
    "fr": ("French", "Français"), "hu": ("Hungarian", "Magyar"), "id": ("Indonesian", "Bahasa Indonesia"),
    "it": ("Italian", "Italiano"), "ja": ("Japanese", "日本語"), "ko": ("Korean", "한국어"),
    "nb": ("Norwegian", "Norsk"), "nl": ("Dutch", "Nederlands"), "pl": ("Polish", "Polski"),
    "pt-BR": ("Portuguese (Brazil)", "Português (Brasil)"), "pt-PT": ("Portuguese (Portugal)", "Português"),
    "ro": ("Romanian", "Română"), "ru": ("Russian", "Русский"), "sv": ("Swedish", "Svenska"),
    "th": ("Thai", "ไทย"), "tr": ("Turkish", "Türkçe"), "uk": ("Ukrainian", "Українська"),
    "vi": ("Vietnamese", "Tiếng Việt"), "zh-Hans": ("Chinese (Simplified)", "简体中文"),
    "zh-Hant": ("Chinese (Traditional)", "繁體中文"),
}

STEAM_MARKER = re.compile(r"<!-- steam-names (\{.*\}) -->")


def english_name(tag):
    return LANGUAGES.get(tag, (tag, tag))[0]


def native_name(tag):
    return LANGUAGES.get(tag, (tag, tag))[1]


def game_folder(game_id):
    """The registry folder of a game ID: `steam:620` → `steam-620`."""
    return game_id.replace(":", "-")


def previous_names(path):
    """Steam names and pictures a GAMES.md recorded in its `<!-- steam-names {...} -->` marker; {} when none."""
    try:
        with open(path, encoding="utf-8") as f:
            match = STEAM_MARKER.search(f.read())
        return json.loads(match.group(1)) if match else {}
    except (OSError, ValueError):
        return {}


def steam_details(app_id):
    """{"name", "image"} from the Steam store, or None when it can't be reached or doesn't know the app."""
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&filters=basic"
    request = urllib.request.Request(url, headers={"User-Agent": "ailocalpack-registry"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            entry = json.load(response).get(str(app_id), {})
    except (OSError, ValueError):
        return None
    if not entry.get("success"):
        return None
    data = entry.get("data", {})
    image = (data.get("header_image") or "").split("?")[0]
    return {"name": data.get("name") or f"Steam app {app_id}", "image": image}


def read_manifest(root, pack):
    """The manifest an index pack entry points to; {} when it can't be read."""
    try:
        with open(os.path.join(root, pack["manifest"]), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}
