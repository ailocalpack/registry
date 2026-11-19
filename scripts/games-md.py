#!/usr/bin/env python3
"""Writes GAMES.md: every game with a translation, its languages and what each language has (text, voice, textures).

    python3 -I scripts/games-md.py <index.json> [--root .] [--out GAMES.md]

<index.json> is the built index (`ailocalpack index build`, with ratings so `verified` is current); <root> is the
registry checkout, read for the manifests (voice and texture parts). Steam names and header images come from the
Steam store; when the store can't be reached, the names the previous GAMES.md recorded are kept, so a flaky store
never turns into a pull request. The output has no timestamp: it changes only when the translations do.
"""

import argparse
import json
import os
import re
import sys
import urllib.request

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
YES, NO = "✅", "➖"
APP = "https://github.com/ailocalpack/ailocalpack"


def previous_names(path):
    try:
        with open(path, encoding="utf-8") as f:
            match = STEAM_MARKER.search(f.read())
        return json.loads(match.group(1)) if match else {}
    except (OSError, ValueError):
        return {}


def steam_details(app_id):
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


def manifest(root, pack):
    try:
        with open(os.path.join(root, pack["manifest"]), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, KeyError):
        return {}


def escape(text):
    return text.replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")


def language_cell(tag):
    english, native = LANGUAGES.get(tag, (tag, tag))
    return f"**{english}**" if english == native else f"**{english}**<br><sub>{native} · `{tag}`</sub>"


def pack_line(pack):
    status = "🟢 verified" if pack.get("status") == "verified" else "🟡 alpha"
    coverage = pack.get("coverage") or {}
    total = coverage.get("total") or 0
    percent = f" · {coverage.get('translated', 0) * 100 // total}%" if total else ""
    folder = os.path.dirname(pack["manifest"])
    line = f"[{escape(pack.get('title') or pack['id'])}]({folder}) <sub>{status}{percent} · rev. {pack.get('revision', 1)}"
    likes = (pack.get("rating") or {}).get("likes")
    if likes:
        line += f" · 👍 {likes}"
    if pack.get("discussion"):
        line += f" · [rate]({pack['discussion']})"
    return line + "</sub>"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("index")
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="GAMES.md")
    args = parser.parse_args()

    with open(args.index, encoding="utf-8") as f:
        index = json.load(f)

    known = previous_names(args.out)
    steam = {}
    rows = []
    for game_id, game in index.get("games", {}).items():
        packs = {lang: list(p) for lang, p in (game.get("packs") or {}).items() if p}
        if not packs:
            continue
        if game_id.startswith("steam:"):
            app_id = game_id.split(":", 1)[1]
            details = steam_details(app_id) or known.get(game_id) or {"name": f"Steam app {app_id}", "image": ""}
            steam[game_id] = details
            name, image = details["name"], details["image"]
            link = f"https://store.steampowered.com/app/{app_id}/"
        else:
            name = f"A game added from a folder ({game_id[:7]}…{game_id[-4:]})"
            image, link = "", None
        rows.append((name.casefold(), game_id, name, image, link, packs))
    rows.sort()

    pack_count = sum(len(p) for *_, packs in rows for p in packs.values())
    languages = sorted({lang for *_, packs in rows for lang in packs})

    out = [
        '<p align="center"><img src="assets/registry-icon-512.png" width="96" alt=""></p>',
        "",
        '<h1 align="center">Games with translations</h1>',
        "",
        '<p align="center">',
        f"  <b>{len(rows)}</b> {'game' if len(rows) == 1 else 'games'} · "
        f"<b>{len(languages)}</b> {'language' if len(languages) == 1 else 'languages'} · "
        f"<b>{pack_count}</b> {'translation' if pack_count == 1 else 'translations'}<br>",
        f'  Install any of them in one click with <a href="{APP}">AI Local Pack</a>, or create a new one with AI.',
        "</p>",
        "",
        f"{YES} available · {NO} not yet (voice comes with phase 2, textures with phase 3) · "
        "🟢 verified: confirmed by 3 players · 🟡 alpha: new, not confirmed yet · % of the game's text translated",
        "",
        "| Game | Language | 📝 Text | 🎙️ Voice | 🖼️ Textures | Translations |",
        "| --- | --- | :---: | :---: | :---: | --- |",
    ]
    for _, game_id, name, image, link, packs in rows:
        title = f"[**{escape(name)}**]({link})" if link else f"**{escape(name)}**"
        picture = f'<img src="{image}" width="140" alt=""><br>' if image else ""
        first = True
        for lang in sorted(packs, key=lambda t: LANGUAGES.get(t, (t,))[0]):
            manifests = [manifest(args.root, p) for p in packs[lang]]
            voice = YES if any(m.get("audio") for m in manifests) else NO
            textures = YES if any(m.get("textures") for m in manifests) else NO
            text = YES if any(not m or m.get("strings") or m.get("patch") for m in manifests) else NO
            game_cell = f"{picture}{title}" if first else ""
            first = False
            translations = "<br>".join(pack_line(p) for p in packs[lang])
            out.append(f"| {game_cell} | {language_cell(lang)} | {text} | {voice} | {textures} | {translations} |")

    out += [
        "",
        "Your game isn't here? Open it in AI Local Pack: **Create with AI** makes a translation on your own AI "
        "subscription, or ask for one and other players can take it on.",
        "",
        "<sub>Made by `scripts/games-md.py` from the published index; don't edit by hand.</sub>",
        "",
        f"<!-- steam-names {json.dumps(steam, ensure_ascii=False, sort_keys=True)} -->",
        "",
    ]
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
