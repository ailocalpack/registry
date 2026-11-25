"""What the site (scripts/site.py) uses: language names, game names and pictures from the stores (Steam, GOG) or
the packs' own manifests (`gameName`), manifests. Standard library only; the scripts run with `python3 -I` (they add this folder to
sys.path themselves)."""

import json
import os
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

# Game ID prefix → (store name, where the app finds its games). Epic Games and the EA app have no public lookup
# by the IDs the app records, so their names come from the manifests and they get no store link.
STORES = {
    "steam": ("Steam", "your Steam library"),
    "gog": ("GOG", "your GOG library (GOG Galaxy or Heroic)"),
    "epic": ("Epic Games", "your Epic Games library (the Epic Games Launcher or Heroic)"),
    "ea": ("EA app", "your EA app library"),
}


def english_name(tag):
    return LANGUAGES.get(tag, (tag, tag))[0]


def native_name(tag):
    return LANGUAGES.get(tag, (tag, tag))[1]


def game_folder(game_id):
    """The registry folder of a game ID: `steam:620` → `steam-620`."""
    return game_id.replace(":", "-")


def store_of(game_id):
    """The game ID's store prefix (`steam`, `gog`, `epic`, `ea`), or None for a game added from a folder."""
    prefix = game_id.split(":", 1)[0]
    return prefix if prefix in STORES else None


def previous_names(path):
    """What the stores answered at the previous publish (store-names.json: game ID → {"name", "image"}, GOG also
    "store"); {} when there is no such file or it can't be read."""
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "ailocalpack-registry"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def steam_details(app_id):
    """{"name", "image"} from the Steam store, or None when it can't be reached or doesn't know the app."""
    entry = (_get_json(f"https://store.steampowered.com/api/appdetails?appids={app_id}&filters=basic") or {}).get(str(app_id), {})
    if not isinstance(entry, dict) or not entry.get("success"):
        return None
    data = entry.get("data", {})
    if not data.get("name"):
        return None
    return {"name": data["name"], "image": (data.get("header_image") or "").split("?")[0]}


def gog_details(product_id):
    """{"name", "image", "store"} from GOG's public product API, or None when it can't be reached or doesn't know it."""
    data = _get_json(f"https://api.gog.com/products/{product_id}")
    if not isinstance(data, dict) or not data.get("title"):
        return None
    image = ((data.get("images") or {}).get("logo2x") or "").split("?")[0]
    if image.startswith("//"):
        image = "https:" + image
    card = (data.get("links") or {}).get("product_card") or ""
    return {"name": data["title"], "image": image, "store": card if card.startswith("https://www.gog.com/") else ""}


def store_details(game_id):
    """What the game's store says about it ({"name", "image"}, GOG also "store"), or None: no answer, or a store
    without a public lookup (Epic Games, EA app) or a game added from a folder."""
    store, value = store_of(game_id), game_id.split(":", 1)[-1]
    if store == "steam":
        return steam_details(value)
    if store == "gog":
        return gog_details(value)
    return None


def store_link(game_id, details):
    """The game's store page, or None (Epic Games and EA IDs aren't the store's page addresses)."""
    store, value = store_of(game_id), game_id.split(":", 1)[-1]
    if store == "steam":
        return f"https://store.steampowered.com/app/{value}/"
    if store == "gog":
        return (details or {}).get("store") or None
    return None


def manifest_name(manifests):
    """The `gameName` of the newest manifest that has one, or None (packs from before the app wrote it)."""
    named = [m for m in manifests if isinstance(m.get("gameName"), str) and m["gameName"].strip()]
    if not named:
        return None
    return max(named, key=lambda m: str(m.get("updated", "")))["gameName"].strip()


def fallback_name(game_id):
    """A name for a game no store or manifest names."""
    store = store_of(game_id)
    if store is None:
        return f"A game added from a folder ({game_id[3:10]}…)"
    return f"{STORES[store][0]} game {game_id.split(':', 1)[1]}"


def game_details(game_id, manifests, known, fetch=store_details, known_first=True):
    """{"name", "image", "store", "cached"} for a game: the store's answer (or what <known> recorded of an earlier
    one; <known_first> asks the store only when nothing is known), else the manifests' `gameName`, else a fallback
    name. "cached" is the store's answer to record for next time, or None."""
    answer = None
    if store_of(game_id) is not None:
        answer = (known.get(game_id) or fetch(game_id)) if known_first else (fetch(game_id) or known.get(game_id))
    name = (answer or {}).get("name") or manifest_name(manifests) or fallback_name(game_id)
    return {"name": name, "image": (answer or {}).get("image") or "", "store": store_link(game_id, answer),
            "cached": answer}


def read_manifest(root, pack):
    """The manifest an index pack entry points to; {} when it can't be read."""
    try:
        with open(os.path.join(root, pack["manifest"]), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}
