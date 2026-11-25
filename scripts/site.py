#!/usr/bin/env python3
"""Writes the registry's public site next to index.json on GitHub Pages: a catalog of the games with translations
(search and filters), one page per game, the open translation requests, sitemap.xml, robots.txt and 404.html.

    python3 -I scripts/site.py <index.json> --root . --out _site [--names store-names.json] [--repo ailocalpack/registry]

<index.json> is the built index (with ratings and requests); <root> the registry checkout (manifests for the engine,
builds and agent; site/ for the stylesheet, script and icon); <out> the Pages folder, where games/ is already
copied (a game page is games/<game folder>/index.html, beside its language folders). Steam and GOG names and
pictures come from the store, else from <names> (the store-names.json of the previous publish, so a flaky store
never loses a name); what the stores answered is written to <out>/store-names.json for the next run. Epic Games and
EA app games (no public lookup), manual games and a game no store answer is known for take the name their newest
manifest records (`gameName`), else "Steam game <id>" or the like. Every page is plain HTML that works without JavaScript; site.js adds the filters, the reader's
language and relative times. Nothing in the output depends on the clock, only on the index.
"""

import argparse
import html
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registry_common import (  # noqa: E402
    LANGUAGES, STORES, english_name, game_details, game_folder, native_name, previous_names, read_manifest, store_details,
    store_of)

APP = "https://github.com/ailocalpack/ailocalpack"
DOWNLOAD = APP + "/releases/latest"
# The release's files per platform (the app's release workflow names them AiLocalPack-<rid>-Setup.exe and so on):
# (rid, name, hint, icon, installer, portable or None). The download menu links straight to them.
PLATFORMS = [
    ("win-x64", "Windows", "most PCs", "o-windows", "Setup.exe", "Portable.zip"),
    ("win-arm64", "Windows on ARM", "Snapdragon laptops", "o-windows", "Setup.exe", "Portable.zip"),
    ("osx-arm64", "Mac with Apple chip", "M1, M2, M3…", "b-apple", "Setup.pkg", "Portable.zip"),
    ("osx-x64", "Mac with Intel", "older Macs", "b-apple", "Setup.pkg", "Portable.zip"),
    ("linux-x64", "Linux", "64-bit, no installing", "b-linux", "AppImage", None),
]
ENGINES = {"unity": "Unity", "unreal": "Unreal", "godot": "Godot", "renpy": "Ren'Py", "rpgmaker": "RPG Maker",
           "other": "Other engine"}
AGENTS = {"claude-code": "Claude Code", "codex": "Codex"}
OS_NAMES = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}
STAGES = {"setup": "setting up", "extract": "reading the game", "study": "studying the game",
          "glossary": "glossary", "translate": "translating", "build": "building", "done": "done"}


def e(text):
    return html.escape(str(text), quote=True)


def attr_json(value):
    return e(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def day(iso):
    """`2026-11-14T19:11:22Z` → `14 Nov 2026`; the text itself when it isn't a date."""
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return f"{d.day} {d:%b %Y}"
    except ValueError:
        return str(iso)


def icon(name, cls="i"):
    return f'<svg class="{cls}" aria-hidden="true"><use href="#{name}"/></svg>'


def asset_url(rid, file):
    sep = "." if file == "AppImage" else "-"
    return f"{DOWNLOAD}/download/AiLocalPack-{rid}{sep}{file}"


def download(label, kind="accent", sym="i-download", size=" sm", end=False, attrs=""):
    """A button that opens the download menu: every platform's installer and portable archive of the latest release.
    A <details>, so it opens without JavaScript; site.js closes it on a click outside or Esc, keeps it on screen and
    puts the reader's own computer first."""
    rows = []
    for rid, name, hint, os_icon, installer, portable in PLATFORMS:
        ext = "." + installer.split(".")[-1] if "." in installer else "." + installer
        alt = (f'<a class="dl-alt" href="{asset_url(rid, portable)}" title="Runs without installing">Portable <code>.zip</code></a>'
               if portable else '<span class="dl-alt none"></span>')
        rows.append(f'<li data-rid="{rid}"><a class="dl-main" href="{asset_url(rid, installer)}">{icon(os_icon)}'
                    f'<span class="dl-name"><b>{e(name)}</b><small>{e(hint)}</small></span><code class="dl-ext">{ext}</code></a>{alt}</li>')
    return (f'<details class="dl{" end" if end else ""}"{attrs}><summary class="btn {kind}{size}">{icon(sym, "i sm")}<span>{label}</span>'
            f'{icon("i-chev-down", "i sm chev")}</summary><div class="dl-menu"><p class="dl-title">Download AI Local Pack</p>'
            f'<ul>{"".join(rows)}</ul><a class="dl-all" href="{DOWNLOAD}">All files and what’s new{icon("i-arrow", "i sm")}</a></div></details>')


# ---------------------------------------------------------------- data

class Game:
    def __init__(self, game_id, name, image, store, engine, packs, requests):
        self.id, self.name, self.image, self.store = game_id, name, image, store
        self.engine, self.packs, self.requests = engine, packs, requests
        self.folder = game_folder(game_id)

    @property
    def pack_count(self):
        return sum(len(p) for p in self.packs.values())

    def likes(self, lang=None):
        packs = self.packs.get(lang, []) if lang else [p for ps in self.packs.values() for p in ps]
        return sum((p.get("rating") or {}).get("likes", 0) for p in packs)

    def works(self, lang=None):
        packs = self.packs.get(lang, []) if lang else [p for ps in self.packs.values() for p in ps]
        return sum((p.get("rating") or {}).get("works", 0) for p in packs)

    def status(self, lang):
        packs = self.packs.get(lang)
        if not packs:
            return None
        return "verified" if any(p.get("status") == "verified" for p in packs) else "alpha"

    def updated(self):
        return max((p.get("updated", "") for ps in self.packs.values() for p in ps), default="")


def engine_of(manifests):
    """The toolkit tool of a recipe pack (Unity, Godot…); a binary patch pack's engine is unknown: "other"."""
    for m in manifests:
        tool = (m.get("recipe") or {}).get("tool")
        if tool in ENGINES:
            return tool
    return "other" if manifests else None


def collect(index, root, known, fetch=store_details, answers=None):
    """The games to show; <answers> (when given) gets what the stores answered, game ID → details."""
    games = []
    for game_id, entry in (index.get("games") or {}).items():
        if entry.get("optOut") or (entry.get("antiCheat") and not entry.get("antiCheatAllowed")):
            continue  # never shown: the app blocks these games
        packs = {lang: [dict(p) for p in ps] for lang, ps in (entry.get("packs") or {}).items() if ps}
        requests = {lang: r for lang, r in (entry.get("requests") or {}).items() if lang not in packs}
        if not packs and not requests:
            continue
        manifests = []
        for ps in packs.values():
            for p in ps:
                p["_manifest"] = read_manifest(root, p)
                manifests.append(p["_manifest"])
        details = game_details(game_id, manifests, known, fetch, known_first=False)
        if details["cached"] and answers is not None:
            answers[game_id] = details["cached"]
        games.append(Game(game_id, details["name"], details["image"], details["store"], engine_of(manifests), packs, requests))
    games.sort(key=lambda g: (-g.likes(), -g.pack_count, g.name.casefold()))
    return games


# ---------------------------------------------------------------- layout

SPRITE = """<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></symbol>
<symbol id="i-x" viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></symbol>
<symbol id="i-languages" viewBox="0 0 24 24"><path d="m5 8 6 6M4 14l6-6 2-3M2 5h12M7 2h1M22 22l-5-10-5 10M14 18h6"/></symbol>
<symbol id="i-thumb" viewBox="0 0 24 24"><path d="M7 10v12M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/></symbol>
<symbol id="i-check" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></symbol>
<symbol id="i-shield" viewBox="0 0 24 24"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></symbol>
<symbol id="i-flask" viewBox="0 0 24 24"><path d="M10 2v7.53a2 2 0 0 1-.21.9L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.07-10.12a2 2 0 0 1-.21-.9V2M8.5 2h7M7 16h10"/></symbol>
<symbol id="i-hand" viewBox="0 0 24 24"><path d="M18 11V6a2 2 0 0 0-4 0v1M14 10V4a2 2 0 0 0-4 0v2M10 10.5V6a2 2 0 0 0-4 0v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/></symbol>
<symbol id="i-sparkles" viewBox="0 0 24 24"><path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.13-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.13a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.13 1.58a.5.5 0 0 1 0 .96L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 6.13a.5.5 0 0 1-.96 0z"/><path d="M20 3v4M22 5h-4"/></symbol>
<symbol id="i-download" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></symbol>
<symbol id="i-grid" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></symbol>
<symbol id="i-list" viewBox="0 0 24 24"><path d="M3 12h.01M3 18h.01M3 6h.01M8 12h13M8 18h13M8 6h13"/></symbol>
<symbol id="i-filter" viewBox="0 0 24 24"><path d="M10 20a1 1 0 0 0 .55.9l2 1A1 1 0 0 0 14 21v-7a2 2 0 0 1 .52-1.34L21.74 4.67A1 1 0 0 0 21 3H3a1 1 0 0 0-.74 1.67l7.22 7.99A2 2 0 0 1 10 14z"/></symbol>
<symbol id="i-arrow" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></symbol>
<symbol id="i-chev" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></symbol>
<symbol id="i-chev-down" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></symbol>
<symbol id="o-windows" viewBox="0 0 24 24"><rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8M12 17v4"/></symbol>
<symbol id="i-msg" viewBox="0 0 24 24"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/></symbol>
<symbol id="i-folder" viewBox="0 0 24 24"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></symbol>
<symbol id="i-loader" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-6.22-8.56"/></symbol>
<symbol id="b-github" viewBox="0 0 24 24"><path fill="currentColor" stroke="none" d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></symbol>
<symbol id="b-steam" viewBox="0 0 24 24"><path fill="currentColor" stroke="none" d="M11.979 0C5.678 0 .511 4.86.022 11.037l6.432 2.658c.545-.371 1.203-.59 1.912-.59.063 0 .125.004.188.006l2.861-4.142V8.91c0-2.495 2.028-4.524 4.524-4.524 2.494 0 4.524 2.031 4.524 4.527s-2.03 4.525-4.524 4.525h-.105l-4.076 2.911c0 .052.004.105.004.159 0 1.875-1.515 3.396-3.39 3.396-1.635 0-3.016-1.173-3.331-2.727L.436 15.27C1.862 20.307 6.486 24 11.979 24c6.627 0 11.999-5.373 11.999-12S18.605 0 11.979 0zM7.54 18.21l-1.473-.61c.262.543.714.999 1.314 1.25 1.297.539 2.793-.076 3.332-1.375.263-.63.264-1.319.005-1.949s-.75-1.121-1.377-1.383c-.624-.26-1.29-.249-1.878-.03l1.523.63c.956.4 1.409 1.5 1.009 2.455-.397.957-1.497 1.41-2.454 1.012H7.54zm11.415-9.303c0-1.662-1.353-3.015-3.015-3.015-1.665 0-3.015 1.353-3.015 3.015 0 1.665 1.35 3.015 3.015 3.015 1.663 0 3.015-1.35 3.015-3.015zm-5.273-.005c0-1.252 1.013-2.266 2.265-2.266 1.249 0 2.266 1.014 2.266 2.266 0 1.251-1.017 2.265-2.266 2.265-1.253 0-2.265-1.014-2.265-2.265z"/></symbol>
<symbol id="b-gog" viewBox="0 0 24 24"><path fill="currentColor" stroke="none" d="M7.15 15.24H4.36a.4.4 0 0 0-.4.4v2c0 .21.18.4.4.4h2.8v1.32h-3.5c-.56 0-1.02-.46-1.02-1.03v-3.39c0-.56.46-1.02 1.03-1.02h3.48v1.32zM8.16 11.54c0 .58-.47 1.05-1.05 1.05H2.63v-1.35h3.78a.4.4 0 0 0 .4-.4V6.39a.4.4 0 0 0-.4-.4H4.39a.4.4 0 0 0-.41.4v2.02c0 .23.18.4.4.4H6v1.35H3.68c-.58 0-1.05-.46-1.05-1.04V5.68c0-.57.47-1.04 1.05-1.04H7.1c.58 0 1.05.47 1.05 1.04v5.86zM21.36 19.36h-1.32v-4.12h-.93a.4.4 0 0 0-.4.4v3.72h-1.33v-4.12h-.93a.4.4 0 0 0-.4.4v3.72h-1.33v-4.42c0-.56.46-1.02 1.03-1.02h5.61v5.44zM21.37 11.54c0 .58-.47 1.05-1.05 1.05h-4.48v-1.35h3.78a.4.4 0 0 0 .4-.4V6.39a.4.4 0 0 0-.4-.4h-2.03a.4.4 0 0 0-.4.4v2.02c0 .23.18.4.4.4h1.62v1.35H16.9c-.58 0-1.05-.46-1.05-1.04V5.68c0-.57.47-1.04 1.05-1.04h3.43c.58 0 1.05.47 1.05 1.04v5.86zM13.72 4.64h-3.44c-.58 0-1.04.47-1.04 1.04v3.44c0 .58.46 1.04 1.04 1.04h3.44c.57 0 1.04-.46 1.04-1.04V5.68c0-.57-.47-1.04-1.04-1.04m-.3 1.75v2.02a.4.4 0 0 1-.4.4h-2.03a.4.4 0 0 1-.4-.4V6.4c0-.22.17-.4.4-.4H13c.23 0 .4.18.4.4zM12.63 13.92H9.24c-.57 0-1.03.46-1.03 1.02v3.39c0 .57.46 1.03 1.03 1.03h3.39c.57 0 1.03-.46 1.03-1.03v-3.39c0-.56-.46-1.02-1.03-1.02m-.3 1.72v2a.4.4 0 0 1-.4.4v-.01H9.94a.4.4 0 0 1-.4-.4v-1.99c0-.22.18-.4.4-.4h2c.22 0 .4.18.4.4zM23.49 1.1a1.74 1.74 0 0 0-1.24-.52H1.75A1.74 1.74 0 0 0 0 2.33v19.34a1.74 1.74 0 0 0 1.75 1.75h20.5A1.74 1.74 0 0 0 24 21.67V2.33c0-.48-.2-.92-.51-1.24m0 20.58a1.23 1.23 0 0 1-1.24 1.24H1.75A1.23 1.23 0 0 1 .5 21.67V2.33a1.23 1.23 0 0 1 1.24-1.24h20.5a1.24 1.24 0 0 1 1.24 1.24v19.34z"/></symbol>
<symbol id="b-apple" viewBox="0 0 24 24"><path fill="currentColor" stroke="none" d="M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.039 1.52-.065 2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948 1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04 2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09-4.61 1.09zM15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.701"/></symbol>
<symbol id="b-linux" viewBox="0 0 24 24"><path fill="currentColor" stroke="none" d="M12.504 0c-.155 0-.315.008-.48.021-4.226.333-3.105 4.807-3.17 6.298-.076 1.092-.3 1.953-1.05 3.02-.885 1.051-2.127 2.75-2.716 4.521-.278.832-.41 1.684-.287 2.489a.424.424 0 00-.11.135c-.26.268-.45.6-.663.839-.199.199-.485.267-.797.4-.313.136-.658.269-.864.68-.09.189-.136.394-.132.602 0 .199.027.4.055.536.058.399.116.728.04.97-.249.68-.28 1.145-.106 1.484.174.334.535.47.94.601.81.2 1.91.135 2.774.6.926.466 1.866.67 2.616.47.526-.116.97-.464 1.208-.946.587-.003 1.23-.269 2.26-.334.699-.058 1.574.267 2.577.2.025.134.063.198.114.333l.003.003c.391.778 1.113 1.132 1.884 1.071.771-.06 1.592-.536 2.257-1.306.631-.765 1.683-1.084 2.378-1.503.348-.199.629-.469.649-.853.023-.4-.2-.811-.714-1.376v-.097l-.003-.003c-.17-.2-.25-.535-.338-.926-.085-.401-.182-.786-.492-1.046h-.003c-.059-.054-.123-.067-.188-.135a.357.357 0 00-.19-.064c.431-1.278.264-2.55-.173-3.694-.533-1.41-1.465-2.638-2.175-3.483-.796-1.005-1.576-1.957-1.56-3.368.026-2.152.236-6.133-3.544-6.139zm.529 3.405h.013c.213 0 .396.062.584.198.19.135.33.332.438.533.105.259.158.459.166.724 0-.02.006-.04.006-.06v.105a.086.086 0 01-.004-.021l-.004-.024a1.807 1.807 0 01-.15.706.953.953 0 01-.213.335.71.71 0 00-.088-.042c-.104-.045-.198-.064-.284-.133a1.312 1.312 0 00-.22-.066c.05-.06.146-.133.183-.198.053-.128.082-.264.088-.402v-.02a1.21 1.21 0 00-.061-.4c-.045-.134-.101-.2-.183-.333-.084-.066-.167-.132-.267-.132h-.016c-.093 0-.176.03-.262.132a.8.8 0 00-.205.334 1.18 1.18 0 00-.09.4v.019c.002.089.008.179.02.267-.193-.067-.438-.135-.607-.202a1.635 1.635 0 01-.018-.2v-.02a1.772 1.772 0 01.15-.768c.082-.22.232-.406.43-.533a.985.985 0 01.594-.2zm-2.962.059h.036c.142 0 .27.048.399.135.146.129.264.288.344.465.09.199.14.4.153.667v.004c.007.134.006.2-.002.266v.08c-.03.007-.056.018-.083.024-.152.055-.274.135-.393.2.012-.09.013-.18.003-.267v-.015c-.012-.133-.04-.2-.082-.333a.613.613 0 00-.166-.267.248.248 0 00-.183-.064h-.021c-.071.006-.13.04-.186.132a.552.552 0 00-.12.27.944.944 0 00-.023.33v.015c.012.135.037.2.08.334.046.134.098.2.166.268.01.009.02.018.034.024-.07.057-.117.07-.176.136a.304.304 0 01-.131.068 2.62 2.62 0 01-.275-.402 1.772 1.772 0 01-.155-.667 1.759 1.759 0 01.08-.668 1.43 1.43 0 01.283-.535c.128-.133.26-.2.418-.2zm1.37 1.706c.332 0 .733.065 1.216.399.293.2.523.269 1.052.468h.003c.255.136.405.266.478.399v-.131a.571.571 0 01.016.47c-.123.31-.516.643-1.063.842v.002c-.268.135-.501.333-.775.465-.276.135-.588.292-1.012.267a1.139 1.139 0 01-.448-.067 3.566 3.566 0 01-.322-.198c-.195-.135-.363-.332-.612-.465v-.005h-.005c-.4-.246-.616-.512-.686-.71-.07-.268-.005-.47.193-.6.224-.135.38-.271.483-.336.104-.074.143-.102.176-.131h.002v-.003c.169-.202.436-.47.839-.601.139-.036.294-.065.466-.065zm2.8 2.142c.358 1.417 1.196 3.475 1.735 4.473.286.534.855 1.659 1.102 3.024.156-.005.33.018.513.064.646-1.671-.546-3.467-1.089-3.966-.22-.2-.232-.335-.123-.335.59.534 1.365 1.572 1.646 2.757.13.535.16 1.104.021 1.67.067.028.135.06.205.067 1.032.534 1.413.938 1.23 1.537v-.043c-.06-.003-.12 0-.18 0h-.016c.151-.467-.182-.825-1.065-1.224-.915-.4-1.646-.336-1.77.465-.008.043-.013.066-.018.135-.068.023-.139.053-.209.064-.43.268-.662.669-.793 1.187-.13.533-.17 1.156-.205 1.869v.003c-.02.334-.17.838-.319 1.35-1.5 1.072-3.58 1.538-5.348.334a2.645 2.645 0 00-.402-.533 1.45 1.45 0 00-.275-.333c.182 0 .338-.03.465-.067a.615.615 0 00.314-.334c.108-.267 0-.697-.345-1.163-.345-.467-.931-.995-1.788-1.521-.63-.4-.986-.87-1.15-1.396-.165-.534-.143-1.085-.015-1.645.245-1.07.873-2.11 1.274-2.763.107-.065.037.135-.408.974-.396.751-1.14 2.497-.122 3.854a8.123 8.123 0 01.647-2.876c.564-1.278 1.743-3.504 1.836-5.268.048.036.217.135.289.202.218.133.38.333.59.465.21.201.477.335.876.335.039.003.075.006.11.006.412 0 .73-.134.997-.268.29-.134.52-.334.74-.4h.005c.467-.135.835-.402 1.044-.7zm2.185 8.958c.037.6.343 1.245.882 1.377.588.134 1.434-.333 1.791-.765l.211-.01c.315-.007.577.01.847.268l.003.003c.208.199.305.53.391.876.085.4.154.78.409 1.066.486.527.645.906.636 1.14l.003-.007v.018l-.003-.012c-.015.262-.185.396-.498.595-.63.401-1.746.712-2.457 1.57-.618.737-1.37 1.14-2.036 1.191-.664.053-1.237-.2-1.574-.898l-.005-.003c-.21-.4-.12-1.025.056-1.69.176-.668.428-1.344.463-1.897.037-.714.076-1.335.195-1.814.12-.465.308-.797.641-.984l.045-.022zm-10.814.049h.01c.053 0 .105.005.157.014.376.055.706.333 1.023.752l.91 1.664.003.003c.243.533.754 1.064 1.189 1.637.434.598.77 1.131.729 1.57v.006c-.057.744-.48 1.148-1.125 1.294-.645.135-1.52.002-2.395-.464-.968-.536-2.118-.469-2.857-.602-.369-.066-.61-.2-.723-.4-.11-.2-.113-.602.123-1.23v-.004l.002-.003c.117-.334.03-.752-.027-1.118-.055-.401-.083-.71.043-.94.16-.334.396-.4.69-.533.294-.135.64-.202.915-.47h.002v-.002c.256-.268.445-.601.668-.838.19-.201.38-.336.663-.336zm7.159-9.074c-.435.201-.945.535-1.488.535-.542 0-.97-.267-1.28-.466-.154-.134-.28-.268-.373-.335-.164-.134-.144-.333-.074-.333.109.016.129.134.199.2.096.066.215.2.36.333.292.2.68.467 1.167.467.485 0 1.053-.267 1.398-.466.195-.135.445-.334.648-.467.156-.136.149-.267.279-.267.128.016.034.134-.147.332a8.097 8.097 0 01-.69.468zm-1.082-1.583V5.64c-.006-.02.013-.042.029-.05.074-.043.18-.027.26.004.063 0 .16.067.15.135-.006.049-.085.066-.135.066-.055 0-.092-.043-.141-.068-.052-.018-.146-.008-.163-.065zm-.551 0c-.02.058-.113.049-.166.066-.047.025-.086.068-.14.068-.05 0-.13-.02-.136-.068-.01-.066.088-.133.15-.133.08-.031.184-.047.259-.005.019.009.036.03.03.05v.02h.003z"/></symbol>
</defs></svg>"""


class Site:
    def __init__(self, repo, base_url):
        self.repo = repo
        self.base = base_url.rstrip("/") + "/"
        self.github = f"https://github.com/{repo}"

    def page(self, *, path, title, description, body, active, image=None, prefix=None, page_kind="other"):
        """One HTML page at <path> (relative to the site root, "" = the home page)."""
        depth = path.count("/")
        pre = prefix if prefix is not None else "../" * depth
        canonical = self.base + path
        nav = [("", "Translations", "catalog"), ("requests/", "Requests", "requests"), ("#how", "How it works", "how")]
        current = ' aria-current="page"'
        nav_html = "".join(f'<a href="{pre}{href}"{current if key == active else ""}>{label}</a>'
                           for href, label, key in nav)
        og_image = f'<meta property="og:image" content="{e(image)}">\n' if image else ""
        return f"""<!doctype html>
<html lang="en" class="no-js">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="AI Local Pack">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{e(canonical)}">
{og_image}<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}">
<meta name="color-scheme" content="dark light">
<link rel="icon" href="{pre}assets/icon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&amp;family=Manrope:wght@600;700;800&amp;display=swap">
<link rel="stylesheet" href="{pre}assets/site.css">
<script src="{pre}assets/site.js" defer></script>
</head>
<body data-page="{page_kind}">
{SPRITE}
<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="wrap">
  <a class="logo" href="{pre}"><span class="mark"><img src="{pre}assets/icon.svg" alt="" width="30" height="30"></span>AI Local Pack</a>
  <nav class="main" aria-label="Main">{nav_html}</nav>
  <div class="right">
    <a class="btn ghost sm hide-phone" href="{APP}">{icon("b-github", "i sm")}GitHub</a>
    {download("Get the app", end=True)}
  </div>
</div></header>
<main id="main">
{body}
</main>
<footer><div class="wrap">
  <span>Translations: CC BY-SA 4.0 · App: Apache-2.0</span>
  <a href="{self.github}/blob/master/LEGAL.md">Legal &amp; takedown</a>
  <a href="{self.github}/blob/master/LEGAL.md#studio-opt-out">Studio opt-out</a>
  <a href="{self.github}">Registry on GitHub</a>
  <a href="{pre}index.json">index.json</a>
  <span class="sp"></span>
  <span>Fan translations, not made or endorsed by the games' studios. Please own the games you translate.</span>
</div></footer>
</body>
</html>
"""

    # ------------------------------------------------------------ pieces

    @staticmethod
    def cover(game, pre, extra=""):
        img = (f'<img src="{e(game.image)}" alt="" loading="lazy" width="460" height="215" onerror="this.remove()">'
               if game.image else "")
        return (f'<div class="cover">{img}<div class="fallback" aria-hidden="true">{e(game.name)}</div>'
                f'{extra}</div>')

    @staticmethod
    def badge(status, text=None):
        if status == "verified":
            return f'<span class="badge verified">{icon("i-shield", "i sm")}{text or "Verified"}</span>'
        if status == "alpha":
            return f'<span class="badge alpha">{icon("i-flask", "i sm")}{text or "Alpha"}</span>'
        return ""

    @staticmethod
    def lang_chip(lang, cls=""):
        return f'<span class="lang {cls}" data-lang="{e(lang)}" title="{e(english_name(lang))}">{e(native_name(lang))}</span>'

    def card(self, game):
        langs = sorted(game.packs, key=lambda t: -len(game.packs[t]))
        stats = {lang: [game.status(lang), game.likes(lang), game.works(lang)] for lang in game.packs}
        votes = {lang: r.get("votes", 0) for lang, r in game.requests.items()}
        status = ""
        if len(langs) == 1:
            status = self.badge(game.status(langs[0]))
        chips = "".join(self.lang_chip(lang) for lang in langs)
        chips += "".join(self.lang_chip(lang, "wanted") for lang in sorted(game.requests))
        engine = ENGINES.get(game.engine, "")
        return f"""<a class="card" href="games/{e(game.folder)}/" data-name="{e(game.name.casefold())}" data-title="{e(game.name)}" data-engine="{e(game.engine or "")}" data-stats="{attr_json(stats)}" data-votes="{attr_json(votes)}" data-updated="{e(game.updated())}" data-likes="{game.likes()}" data-works="{game.works()}">
  {self.cover(game, "", f'<div class="status">{status}</div>')}
  <div class="body">
    <h3>{e(game.name)}</h3>
    <div class="langs">{chips}</div>
    <div class="meta"><span class="likes" title="Likes">{icon("i-thumb", "i sm")}<b>{game.likes()}</b></span><span class="works" title="Players who confirmed it works">{icon("i-check", "i sm")}<b>{game.works()}</b></span><span class="engine-name">{e(engine)}</span></div>
  </div>
</a>"""

    def claim_text(self, claim):
        by = f'@{e(claim.get("by", ""))}'
        state = claim.get("state")
        if state == "built":
            return f"{by} has a draft and is trying it in game"
        if state == "published":
            return f"{by} published it, waiting for the registry"
        stage = STAGES.get(claim.get("stage", ""), "working")
        return f"{by} is on it · {stage} · {claim.get('percent', 0)}%"

    def request_row(self, game, lang, request, pre):
        claim = request.get("claim")
        votes = request.get("votes", 0)
        done = len(game.packs)
        other = plural(done, "other language", "other languages") + " done" if done else "No translations yet"
        claim_html = (f'<span class="claim">{icon("i-loader", "i sm")}{self.claim_text(claim)}</span>'
                      if claim else "")
        discussion = e(request.get("discussion", self.github + "/discussions"))
        primary = (f'<a class="btn ghost sm" href="{discussion}">{icon("i-msg", "i sm")}Follow</a>' if claim else
                   download("Translate with AI", "gen", "i-sparkles"))
        thumb = (f'<img src="{e(game.image)}" alt="" loading="lazy" width="92" height="43" onerror="this.remove()">'
                 if game.image else "")
        return f"""<div class="req" data-lang="{e(lang)}" data-votes="{votes}">
  <div class="votes"><b>{votes}</b><span>asked</span></div>
  <a class="thumb" href="{pre}games/{e(game.folder)}/" tabindex="-1" aria-hidden="true">{thumb}</a>
  <div class="what"><h3><a href="{pre}games/{e(game.folder)}/">{e(game.name)}</a> <span class="to">→ {e(native_name(lang))}</span></h3>
    <div class="line"><span>{e(ENGINES.get(game.engine, "Engine not known yet") if game.engine else "Engine not known yet")}</span><span>{other}</span>{claim_html}</div></div>
  <div class="acts">{primary}<a class="btn ghost sm" href="{discussion}" aria-label="Me too: add your vote on GitHub, {votes} asked">{icon("i-hand", "i sm")}Me too</a></div>
</div>"""

    def requests_list(self, games):
        rows = [(r.get("votes", 0), g.name.casefold(), lang, g, r)
                for g in games for lang, r in g.requests.items()]
        rows.sort(key=lambda x: (-x[0], x[1], x[2]))
        return rows

    # ------------------------------------------------------------ pages

    def home(self, games, index):
        with_packs = [g for g in games if g.packs]
        packs = sum(g.pack_count for g in games)
        langs = sorted({lang for g in games for lang in g.packs})
        verified = sum(1 for g in games for ps in g.packs.values() for p in ps if p.get("status") == "verified")
        all_langs = sorted({lang for g in games for lang in list(g.packs) + list(g.requests)}, key=english_name)
        options = "".join(f'<option value="{e(t)}">{e(native_name(t))} · {e(english_name(t))}</option>'
                          if native_name(t) != english_name(t) else f'<option value="{e(t)}">{e(english_name(t))}</option>'
                          for t in all_langs)
        names = {t: [english_name(t), native_name(t)] for t in LANGUAGES}
        engines = sorted({g.engine for g in games if g.engine}, key=lambda k: (k == "other", ENGINES[k]))
        engine_checks = "".join(
            f'<label class="check"><input type="checkbox" data-engine="{k}">{e(ENGINES[k])}<span class="n" data-count-engine="{k}"></span></label>'
            for k in engines)
        cards = "".join(self.card(g) for g in games)
        requests = self.requests_list(games)
        wanted = ""
        if requests:
            wanted = f"""<section class="band" id="wanted"><div class="wrap">
  <div class="row-head"><div><h2>Most wanted<span class="in-lang"></span></h2><p class="sub">Players asked for these. Make one with AI and they'll get a notice when it's out.</p></div>
  <a class="more" href="requests/">All requests {icon("i-arrow", "i sm")}</a></div>
  <div class="reqs" data-top="3">{"".join(self.request_row(g, lang, r, "") for _, _, lang, g, r in requests[:30])}</div>
</div></section>"""
        generated = index.get("generated", "")
        body = f"""<section class="hero"><div class="wrap">
  <span class="eyebrow"><span class="dot"></span>{plural(packs, "translation", "translations")} · made by players, checked by players</span>
  <h1>Play the games you own <em>in your language</em></h1>
  <p class="lead">Community translations for {plural(len(with_packs), "game", "games")}, installed in one click and removed just as easily. None for your game yet? Make one with your own AI and share it.</p>
  <form class="search" role="search" action="./" onsubmit="return false">
    {icon("i-search")}
    <label class="sr" for="q">Search games</label>
    <input id="q" type="search" placeholder="Search a game…" autocomplete="off" enterkeyhint="search">
    <kbd class="hide-phone">/</kbd>
  </form>
  <div class="stats">
    <div><b>{len(with_packs)}</b>{"game" if len(with_packs) == 1 else "games"}</div><div><b>{packs}</b>{"translation" if packs == 1 else "translations"}</div><div><b>{len(langs)}</b>{"language" if len(langs) == 1 else "languages"}</div><div><b>{verified}</b>verified</div>
    <div class="when">Updated hourly · last <time datetime="{e(generated)}">{e(day(generated))}</time></div>
  </div>
</div></section>

<div class="wrap catalog" id="browse">
  <div class="drawer-bg" hidden></div>
  <aside class="filters" aria-label="Filters">
    <div class="drawer-head"><h2>Filters</h2><button class="btn ghost sm" type="button" data-close-filters aria-label="Close filters">{icon("i-x", "i sm")}</button></div>
    <div class="fgroup"><h3><label for="lang">Language</label></h3>
      <select class="select" id="lang" data-names="{attr_json(names)}"><option value="*">Any language</option>{options}</select>
      <p class="lang-note">From your browser. Remembered on this device.</p></div>
    <fieldset class="fgroup"><legend><h3>Status</h3></legend><div class="checks">
      <label class="check"><input type="checkbox" data-status="verified">{icon("i-shield", "i sm")}Verified<span class="n" data-count-status="verified"></span></label>
      <label class="check"><input type="checkbox" data-status="alpha">{icon("i-flask", "i sm")}Alpha<span class="n" data-count-status="alpha"></span></label>
      <label class="check"><input type="checkbox" data-status="requested">{icon("i-hand", "i sm")}Requested<span class="n" data-count-status="requested"></span></label>
    </div></fieldset>
    <fieldset class="fgroup"><legend><h3>Engine</h3></legend><div class="checks">{engine_checks}</div></fieldset>
    <div class="fgroup"><h3>Also show</h3><label class="check"><input type="checkbox" data-wanted>Games people asked for</label></div>
  </aside>
  <div class="results-col">
    <div class="toolbar">
      <button class="btn ghost sm filters-btn" type="button" data-open-filters>{icon("i-filter", "i sm")}Filters</button>
      <div class="count" aria-live="polite">{plural(len(games), "game", "games")}</div>
      <span class="sp"></span>
      <label class="sr" for="sort">Sort</label>
      <select class="select" id="sort"><option value="likes">Most liked</option><option value="new">Newest</option><option value="req">Most requested</option><option value="az">A–Z</option></select>
      <div class="seg hide-phone" role="group" aria-label="View">
        <button type="button" data-view="grid" aria-pressed="true" aria-label="Grid">{icon("i-grid", "i sm")}</button>
        <button type="button" data-view="list" aria-pressed="false" aria-label="List">{icon("i-list", "i sm")}</button>
      </div>
    </div>
    <div class="chips"></div>
    <div class="grid" id="results">{cards}</div>
    <div class="empty" id="empty" hidden>
      <div class="ic">{icon("i-sparkles")}</div>
      <h2 data-empty-title>Nothing matches these filters</h2>
      <p data-empty-text>Try removing a filter, or look in another language.</p>
      <div class="acts">
        {download("Translate with AI", "gen", "i-sparkles", "", attrs=" data-empty-ai")}
        {download("Request it in the app", "ghost", "i-hand", "", attrs=" data-empty-ask")}
        <button class="btn ghost" type="button" data-clear>Clear filters</button>
      </div>
      <p class="try" data-empty-try></p>
    </div>
  </div>
</div>

<section class="band" id="how"><div class="wrap">
  <h2>How it works</h2>
  <p class="sub">A free desktop app for Windows, macOS and Linux. No server of ours in between: just the app, GitHub and, if you want, your own AI.</p>
  <div class="steps">
    <div class="step"><div class="ic">{icon("i-search")}</div><h3>Find your game</h3><p>The app finds your games in Steam, Epic Games, GOG and the EA app, or a folder you point it to, and shows the translations for your language with how many players confirmed they work.</p></div>
    <div class="step"><div class="ic">{icon("i-download")}</div><h3>Install in one click</h3><p>The original files are backed up and uninstall puts them back. After a game update the translation is put back or you're told why it can't be.</p></div>
    <div class="step ai"><div class="ic">{icon("i-sparkles")}</div><h3>None yet? Make one</h3><p>Your Claude Code or Codex subscription translates the game, you try it in game, then publish it here for everyone.</p></div>
  </div>
  <p class="cta-row">{download("Get AI Local Pack", size="")}<a class="btn ghost" href="{APP}#readme">Read more</a></p>
</div></section>
{wanted}"""
        return self.page(path="", title="AI Local Pack · Game translations made by players",
                         description=f"Community translations for {plural(len(with_packs), 'game', 'games')} into {plural(len(langs), 'language', 'languages')}. Install in one click with AI Local Pack, or make a new one with your own AI.",
                         body=body, active="catalog", page_kind="catalog")

    def game_page(self, game):
        pre = "../../"
        path = f"games/{game.folder}/"
        order = sorted(game.packs, key=english_name)
        langs_text = ", ".join(english_name(t) for t in order)
        cards = []
        for lang in order:
            packs = sorted(game.packs[lang], key=lambda p: (p.get("status") != "verified",
                                                            -(p.get("rating") or {}).get("likes", 0)))
            for p in packs:
                cards.append(self.pack_card(game, lang, p))
        waiting = ""
        if game.requests:
            rows = "".join(
                f'<div><a href="{e(r.get("discussion", ""))}">{e(native_name(lang))}</a><b>{plural(r.get("votes", 0), "player", "players")}</b></div>'
                for lang, r in sorted(game.requests.items(), key=lambda x: -x[1].get("votes", 0)))
            waiting = f"""<div class="panel ai"><h3>Players are waiting</h3><div class="wantlist">{rows}</div>
  {download("Translate with AI", "gen", "i-sparkles")}</div>"""
        facts = [f'<span class="badge engine">{e(ENGINES[game.engine])}</span>' if game.engine else "",
                 f'<span class="badge engine">{plural(game.pack_count, "translation", "translations")}</span>' if game.pack_count else ""]
        store_icon = {"steam": "b-steam", "gog": "b-gog"}.get(store_of(game.id))
        store = (f'<a class="btn ghost" href="{e(game.store)}">{icon(store_icon, "i sm") if store_icon else ""}Store page</a>'
                 if game.store else "")
        source = store_of(game.id)
        finds = (f"It finds {e(game.name)} in {STORES[source][1]}." if source
                 else f"Add {e(game.name)}'s folder in the app (<b>Add game folder</b>).")
        if game.packs:
            lead = f"Translated by players into {e(langs_text)}. Install from the app: it checks your game build first and keeps the original files."
        else:
            lead = "No translation yet, but players asked for one. You can make it with your own AI in the app."
        bg = f'<div class="bg" style="background-image:url(&quot;{e(game.image)}&quot;)"></div>' if game.image else ""
        translations = (f'<h2>Translations</h2>{"".join(cards)}' if cards else
                        f'<div class="empty"><div class="ic">{icon("i-sparkles")}</div><h2>No translation yet</h2><p>Be the first: the app translates the game with your own AI subscription, you try it in game and publish it here.</p><div class="acts">{download("Translate with AI", "gen", "i-sparkles", "")}</div></div>')
        body = f"""<section class="game-hero">{bg}<div class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="{pre}">Translations</a>{icon("i-chev", "i sm")}<span>{e(game.name)}</span></nav>
  {self.cover(game, pre)}
  <div>
    <h1>{e(game.name)}</h1>
    <div class="facts">{"".join(facts)}</div>
    <p>{lead}</p>
    <div class="acts">{download("Get AI Local Pack", size="")}{store}</div>
  </div>
</div></section>
<div class="wrap gbody">
  <div class="trs">{translations}</div>
  <div class="side">
    <div class="panel"><h3>Install</h3><ol><li>Get <a href="{DOWNLOAD}">AI Local Pack</a> (free, Windows, macOS, Linux).</li><li>{finds}</li><li>Open the game, tab <b>Text</b>, press <b>Install translation</b>.</li></ol></div>
    {waiting}
    <div class="panel"><h3>Something wrong?</h3><p>Reviews and reports live in each translation's GitHub Discussion. The app sends yours after you've played.</p><a href="{self.github}#rating">How ratings work</a></div>
  </div>
</div>"""
        title = (f"{game.name} translations: {langs_text} · AI Local Pack" if game.packs
                 else f"{game.name}: translation requested · AI Local Pack")
        description = (f"Fan translations of {game.name} into {langs_text}, made and checked by players. Install in one click with AI Local Pack."
                       if game.packs else f"Players asked for a translation of {game.name}. Make it with AI Local Pack and your own AI.")
        return path, self.page(path=path, title=title, description=description, body=body, active="catalog",
                               image=game.image or None, page_kind="game")

    def pack_card(self, game, lang, p):
        m = p.get("_manifest") or {}
        rating = p.get("rating") or {}
        works, broken = rating.get("works", 0), rating.get("doesNotWork", 0)
        pct = round(100 * works / (works + broken)) if works + broken else 0
        status = p.get("status")
        badge = self.badge(status, None if status == "verified" else "Alpha · not confirmed by 3 players yet")
        builds = m.get("builds") or []
        if game.id.startswith("steam:") and builds:
            first = builds[0]
            os_name = OS_NAMES.get(first.get("os", ""), "")
            made_for = f"Build {e(first.get('buildId', '?'))}" + (f" · {os_name}" if os_name else "")
            if len(builds) > 1:
                made_for += f" +{len(builds) - 1}"
        elif builds:
            made_for = plural(len(builds), "game version", "game versions")
        else:
            made_for = plural(p.get("buildCount", 0), "build", "builds")
        authors = m.get("authors") or [p.get("author") or {}]
        authors_html = ", ".join(
            f'<a href="https://github.com/{e(a.get("github", ""))}">{e(a.get("name") or a.get("github", ""))}</a>'
            for a in authors[:4] if a.get("github")) + (f" +{len(authors) - 4}" if len(authors) > 4 else "")
        agent = m.get("agent") or {}
        made_with = AGENTS.get(agent.get("id", ""), agent.get("id", "")) if agent else "By hand"
        if agent.get("quality"):
            made_with += f" · {e(str(agent['quality']).capitalize())}"
        coverage = p.get("coverage") or {}
        total = coverage.get("total") or 0
        covers = f"{coverage.get('translated', 0) * 100 // total}% of the text" if total else "—"
        folder = os.path.dirname(p.get("manifest", ""))
        discussion = p.get("discussion")
        reviews = (f'<a href="{e(discussion)}">{icon("i-msg", "i sm")} Reviews on GitHub</a>' if discussion else "")
        return f"""<article class="tr" data-lang="{e(lang)}">
  <div class="head"><span class="lname" title="{e(english_name(lang))}">{e(native_name(lang))}</span>{badge}<span class="rev">«{e(p.get("title") or p.get("id"))}» · revision {e(p.get("revision", 1))}</span><span class="sp"></span>
    {download("Install in the app", end=True)}</div>
  <dl class="facts-grid"><div><dt>Made for</dt><dd>{made_for}</dd></div><div><dt>Authors</dt><dd>{authors_html or "—"}</dd></div><div><dt>Updated</dt><dd><time datetime="{e(p.get("updated", ""))}">{e(day(p.get("updated", "")))}</time></dd></div><div><dt>Made with</dt><dd>{made_with}</dd></div><div><dt>Covers</dt><dd>{covers}</dd></div></dl>
  <div class="foot"><span>{icon("i-thumb", "i sm")}{plural(rating.get("likes", 0), "like", "likes")}</span><span><span class="bar" aria-hidden="true"><i style="width:{pct}%"></i></span>{works} works · {broken} doesn't</span><span class="sp"></span>{reviews}<a href="{self.github}/tree/master/{e(folder)}">{icon("i-folder", "i sm")} Files</a></div>
</article>"""

    def requests_page(self, games):
        pre = "../"
        rows = self.requests_list(games)
        total = sum(v for v, *_ in rows)
        by_lang = {}
        for _, _, lang, _, _ in rows:
            by_lang[lang] = by_lang.get(lang, 0) + 1
        tabs = "".join(f'<button type="button" data-req-tab="{e(t)}" aria-pressed="false">{e(native_name(t))} · {n}</button>'
                       for t, n in sorted(by_lang.items(), key=lambda x: (-x[1], english_name(x[0]))))
        tabs = f'<button type="button" data-req-tab="*" aria-pressed="true">All · {len(rows)}</button>' + tabs
        list_html = ("".join(self.request_row(g, lang, r, pre) for _, _, lang, g, r in rows) if rows else
                     f'<div class="empty"><div class="ic">{icon("i-hand")}</div><h2>No open requests</h2><p>Ask for a translation from the app: open the game, tab Text. Other players add their vote, and translators see the list here.</p><div class="acts">{download("Get AI Local Pack", size="")}</div></div>')
        body = f"""<section class="hero"><div class="wrap narrow">
  <span class="eyebrow"><span class="dot gen"></span>{plural(total, "player is", "players are")} waiting</span>
  <h1>Translations players <em>asked for</em></h1>
  <p class="lead">Each request is a GitHub Discussion, and “Me too” is a 👍 on it. Take one on from the app: the players who asked get a notice when it's out.</p>
</div></section>
<div class="wrap page-body">
  {f'<div class="tabs" role="group" aria-label="Language">{tabs}</div>' if rows else ""}
  <div class="reqs">{list_html}</div>
</div>"""
        return self.page(path="requests/", title="Translation requests · AI Local Pack",
                         description=f"Game translations players asked for: {plural(len(rows), 'open request', 'open requests')}. Make one with AI Local Pack and your own AI.",
                         body=body, active="requests", page_kind="requests")

    def not_found(self):
        body = f"""<section class="hero"><div class="wrap narrow">
  <h1>Page not found</h1>
  <p class="lead">This page isn't here. The game may have no translation yet, or its address changed.</p>
  <p class="cta-row"><a class="btn accent" href="{self.base}">See all translations</a><a class="btn ghost" href="{self.base}requests/">Translation requests</a></p>
</div></section>"""
        return self.page(path="404.html", title="Page not found · AI Local Pack", description="Page not found.",
                         body=body, active="", prefix=self.base, page_kind="other")

    def sitemap(self, games, generated):
        urls = ["", "requests/"] + [f"games/{g.folder}/" for g in games]
        last = {f"games/{g.folder}/": g.updated() for g in games}
        items = []
        for u in urls:
            mod = (last.get(u) or generated or "")[:10]
            items.append(f"  <url><loc>{e(self.base + u)}</loc>" + (f"<lastmod>{e(mod)}</lastmod>" if mod else "") + "</url>")
        return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + "\n".join(items) + "\n</urlset>\n")


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def build(index, root, out, repo, known, fetch=store_details):
    owner, name = repo.split("/", 1)
    site = Site(repo, f"https://{owner}.github.io/{name}/")
    answers = {}
    games = collect(index, root, known, fetch, answers)
    write(os.path.join(out, "index.html"), site.home(games, index))
    write(os.path.join(out, "store-names.json"), json.dumps(answers, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
    for game in games:
        path, text = site.game_page(game)
        write(os.path.join(out, path, "index.html"), text)
    write(os.path.join(out, "requests", "index.html"), site.requests_page(games))
    write(os.path.join(out, "404.html"), site.not_found())
    write(os.path.join(out, "sitemap.xml"), site.sitemap(games, index.get("generated", "")))
    write(os.path.join(out, "robots.txt"), f"User-agent: *\nAllow: /\nSitemap: {site.base}sitemap.xml\n")
    assets = os.path.join(out, "assets")
    os.makedirs(assets, exist_ok=True)
    for source, target in (("site/site.css", "site.css"), ("site/site.js", "site.js"),
                           ("assets/registry-icon.svg", "icon.svg")):
        shutil.copyfile(os.path.join(root, source), os.path.join(assets, target))
    return games


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("index")
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="_site")
    parser.add_argument("--names", help="the previous publish's store-names.json: names when a store doesn't answer")
    parser.add_argument("--repo", default="ailocalpack/registry", help="owner/name: links and the Pages address")
    args = parser.parse_args()
    with open(args.index, encoding="utf-8") as f:
        index = json.load(f)
    games = build(index, args.root, args.out, args.repo, previous_names(args.names))
    print(f"Site: {plural(len(games), 'game', 'games')} into {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
