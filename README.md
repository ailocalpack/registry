<p align="center"><img src="assets/registry-icon-512.png" width="128" alt=""></p>

# AI Local Pack Registry

Community localizations ("packs") for games, installed with the [AI Local Pack](https://github.com/ailocalpack/ailocalpack) app.
The app reads one file, [`index.json`](https://ailocalpack.github.io/registry/index.json), published from this repository to GitHub Pages, and downloads only the packs a player installs.

> **Disclaimer.** Packs are fan translations made by players, often with the help of AI agents. They are not made, checked or endorsed by the games' developers or publishers, and come without any warranty. A pack holds translated text and instructions for rebuilding game files on the player's machine: **no original game text, no game files, no programs** (a mod loader a pack needs, such as BepInEx, is downloaded by the app from its official release, see [Dependencies](#dependencies)). Use packs only with copies of games you own. Rights holders who want a pack removed, or no packs for their game at all: see [takedowns and studio opt-out](LEGAL.md).

## Layout

```
games/<game folder>/<language>/<pack-id>/
  manifest.json            what the pack is, which game builds it fits, how to apply it
  strings/strings.json.gz  the translations (gzip'd JSON string table)
schemas/                   JSON Schemas of manifest.json, the string table, index.json and the policy files
policy/                    lists the app relies on (dependency whitelist, anti-cheat rules and whitelist, opt-outs, verified overrides); maintainers only
ci/ailocalpack-cli         the released ailocalpack CLI CI uses (version + SHA-256 of its archive)
scripts/                   helpers the workflows run
```

- `<game folder>` is the game ID with `:` replaced by `-`: `steam-620` for a Steam game, `fp-<64 hex>` for a game added from a folder (its fingerprint).
- `<language>` is a tag the app knows: `ru`, `de`, `pt-BR`, `es-419`, `zh-Hans`, ...
- `<pack-id>` is the manifest's `id` (lowercase letters, digits and dashes). Several packs per game and language are fine.
- The formats are described by the files in [`schemas/`](schemas) and in the app's [CLAUDE.md](https://github.com/ailocalpack/ailocalpack/blob/master/CLAUDE.md#pack-format).

## Adding or updating a pack

Normally the app does this for you (*Publish* after generating a pack). By hand:

1. Fork this repository and put the pack in its folder, `games/<game folder>/<language>/<pack-id>/`.
2. Set `"status": "alpha"`. Packs become `verified` once players who didn't make it confirm that it works.
3. Updating an existing pack (your own or someone else's) = a new revision of it: raise `revision`, add an entry to `revisions` and yourself to `authors`.
4. Open a pull request that changes **only that one pack folder**.
5. A binary patch pack: its archive `<game folder>-<language>-<pack-id>-<revision>.zip` goes into a release tagged `patches` **in your fork** (an asset, not a commit), and `patch.url` names this repository's copy, `https://github.com/ailocalpack/registry/releases/download/patches/<that name>`. CI checks the fork's file against `patch.size` / `patch.sha256` and copies it here when it merges the pull request.

Check it locally with the CLI (`ailocalpack-cli-<version>-<os>` from the app's [Releases](https://github.com/ailocalpack/ailocalpack/releases), the version in [`ci/ailocalpack-cli`](ci/ailocalpack-cli)):

```sh
ailocalpack pack validate games/<game folder>/<language>/<pack-id>
ailocalpack index build . --out /tmp/index.json
```

## What CI does

| Workflow | When | What |
| --- | --- | --- |
| [Validate](.github/workflows/validate.yml) | every pull request | Downloads the pinned CLI, checks the pull request changes one pack folder (others: maintainers only), the pack is `alpha`, `ailocalpack pack validate` passes (manifest and string table formats, hashes and sizes, folder layout, size limits, links, **no executable files** by extension or by content, every dependency on [`policy/dependencies.json`](policy/dependencies.json)), `schemas/` matches the CLI's, the index still builds, a binary patch pack's archive is in the author's fork with the manifest's size and SHA-256 ([`scripts/check-patch.sh`](scripts/check-patch.sh)). Problems show up as annotations on the files. |
| [Auto-merge](.github/workflows/auto-merge.yml) | after Validate passes | From `master`'s copy of the checks: reads the changed files from the GitHub API, repeats the one-folder, `alpha`, validation and patch archive checks on the pull request's head commit (dependencies against `master`'s whitelist), copies a patch archive to this repository's `patches` release (never replacing a file of the same name with other content), squash-merges it and starts Publish. Pull requests that change anything else wait for a maintainer. |
| [Publish index](.github/workflows/publish.yml) | push to `master`, after a merge, every hour, by hand | `ailocalpack ratings collect` (each pack's Discussion: 👍 and works / doesn't work reports, see [Ratings and `verified`](#ratings-and-verified); opens the Discussion of a pack that has none), `ailocalpack index build` with those ratings (the dependency whitelist goes into `index.json` as `dependencies`), then publishes `index.json`, `games/` and `schemas/` to <https://ailocalpack.github.io/registry/>. Nothing is committed; when the Discussions can't be read the run fails and Pages keeps the previous index. |

CI uses the released CLI: [`ci/ailocalpack-cli`](ci/ailocalpack-cli) names an app release (`version=`) and the SHA-256 of its `ailocalpack-cli-<version>-linux-x64.tar.gz` (`sha256=`, also in the release's `ailocalpack-cli-<version>-SHA256SUMS.txt`); the archive is checked before it is unpacked and holds the `schemas/` the CLI was built with. To move the pin, change both lines (and copy the new `schemas/` if they changed) in a maintainer pull request.

### Checking CI by hand

The workflows are tested with these pull requests whenever they change (open them from a fork, so the fork path is covered):

| Pull request | Expected |
| --- | --- |
| A copy of the sample pack under a new `<pack-id>` (folder and `id` renamed, `revision` 1) | Validate passes, Auto-merge merges it, Publish runs, `index.json` lists the new pack within minutes. Remove it afterwards in a maintainer pull request. |
| The same, plus a file `strings/tool.exe` (any content) | Validate fails: `strings/tool.exe` *has an executable, script or archive extension*. Not merged. |
| The same, with an ELF or `MZ` header saved as `strings/extra.json` | Validate fails: `strings/extra.json` *is a Windows executable (PE)* / *Linux executable (ELF)*. Not merged. |
| `manifest.json` replaced by a link | Validate fails: `manifest.json` *is a link*. Not merged. |
| A pack with `"status": "verified"` | Validate fails on `status`. Not merged. |
| A pack plus a change to `README.md` | Validate fails for a contributor ("one pack per pull request"); for a maintainer it passes and waits for review. |
| A wrong `strings.sha256` in the manifest | Validate fails on `strings.sha256`. Not merged. |
| A pack for a game listed in `policy/opt-out.json` (a maintainer adds `steam:620` on a branch first) | Validate fails on `game`: *on the registry's opt-out list*. Not merged. |
| A pack whose manifest has `"dependencies": [{"id": "bepinex", "version": "5.4.23.2"}]` | Validate passes, Auto-merge merges it (the version is on the whitelist). |
| The same with `"version": "5.4.21"`, or `"id": "melonloader"` | Validate fails on `dependencies[0]`: *not on the registry's dependency whitelist*. Not merged. |

### Repository settings

Kept by hand (they aren't files):

- **Pages**: source *GitHub Actions*.
- **Discussions** on, with a category **`Packs`** in the *Announcement* format (only maintainers and the Publish workflow open Discussions there; players react and comment).
- **Ruleset on `master`**: no deletion, no force push, pull request required with 0 approvals and *Require review from Code Owners*, required status check `validate` (from GitHub Actions). So pack folders merge by themselves and everything with an owner in [CODEOWNERS](.github/CODEOWNERS) waits for a maintainer.
- **Labels** `takedown`, `opt-out`, `block-report` (the issue templates apply them).
- **Team** `ailocalpack/maintainers` with write access (the code owners). Maintainers make their organization membership **public**: with a private one GitHub reports a maintainer's pull request as `CONTRIBUTOR`, and Validate refuses it as a contributor's.

## Dependencies

Packs never ship programs. When a pack needs one (a mod loader such as BepInEx), its manifest names it by ID and version, `"dependencies": [{"id": "bepinex", "version": "5.4.23.2"}]`, and the app downloads it from the project's **official release**, checks its size and SHA-256, and installs it with the pack (removing it again when no installed pack needs it). Only what [`policy/dependencies.json`](policy/dependencies.json) lists can be named ([schema](schemas/dependency-whitelist.schema.json)); CI refuses any other dependency.

Adding a dependency or a version is a maintainer pull request to `policy/dependencies.json`:

- `id` (what manifests name), `name` (shown to players), `homepage` (the official project page).
- Per version, one asset per platform of the **game build** (`windows-x64`, `windows-x86`, `linux-x64`, `macos-x64`, …; a Windows build run through Proton takes the Windows file): the official release URL (a ZIP, `https://`), its `size` and `sha256`, computed from the file downloaded from that URL (`curl -L -o f.zip <url> && shasum -a 256 f.zip`), never copied from elsewhere.
- `layout` when the archive's content doesn't go straight into the game folder: `from` (a folder inside the archive) and `into` (a folder of the game).
- `generated`: what the component creates while the game runs, deleted on uninstall when it wasn't there before (`BepInEx/LogOutput.log`; a folder ends with `/` and is removed only when empty; `*` only in the last part of a file inside a folder, `BepInEx/cache/*`).

Entries are never edited in place once packs use them (a changed hash would make every install fail); a new release is a new version.

## Ratings and `verified`

Every pack has one Discussion in the **Packs** category, opened by Publish index; its first line `<!-- ailocalpack-pack <game id>/<language>/<pack-id> -->` ties it to the pack (don't edit it). Players rate from the app: a 👍 on the Discussion is a like, and *Works* / *Doesn't work* is a comment whose first line is a machine-readable marker (`<!-- ailocalpack-report {...} -->`); only the marker counts, the text around it is for people.

Each run counts, for the pack's **current revision**: one report per account (its latest), not from the pack's authors or bots, from accounts at least 30 days old when they reported, and for a Steam game only reports from a build the manifest lists. Likes leave out the authors and bots. A revision with **3 such "works" reports, and more of them than "doesn't work" ones,** is listed as `verified` in `index.json`; manifests in git stay `alpha`. A new revision starts again from zero.

Maintainers override that for one revision in [`policy/verified.json`](policy/verified.json) (a maintainer pull request):

```json
{"schemaVersion": 1, "packs": [
  {"pack": "steam:620/ru/full", "revision": 3, "status": "verified", "note": "checked by hand"},
  {"pack": "steam:620/de/komplett", "revision": 1, "status": "alpha", "note": "breaks the save menu, see the Discussion"}
]}
```

An entry for an older revision no longer applies; a broken file stops the index build.

## Sample pack

[`games/fp-f362…0288/ru/sample-quest-ru`](games/fp-f362498e21ee992e45352516246500dac24e10b902c54cba2a144c51fe040288/ru/sample-quest-ru) is a Russian pack for *Sample Quest*, a synthetic RPG Maker MZ game that lives in the app repository as [`tests/fixtures/games/sample-quest`](https://github.com/ailocalpack/ailocalpack/tree/master/tests/fixtures/games/sample-quest) (a few text files, nothing to run). Add that folder to the app's library and the pack shows up for it.

## Policy files

Maintainer pull requests only (CODEOWNERS). Each has a JSON Schema in [`schemas/`](schemas); `ailocalpack index build` reads them with the same rules, and a broken file stops the build (the published index never loses a block by accident).

| File | What | Schema |
| --- | --- | --- |
| [`policy/dependencies.json`](policy/dependencies.json) | Executables packs may require, see [Dependencies](#dependencies). Published in `index.json` as `dependencies`. | [dependency-whitelist](schemas/dependency-whitelist.schema.json) |
| [`policy/opt-out.json`](policy/opt-out.json) | Games whose studio asked for no fan translations: `optOut` in the index, their packs left out, new ones refused by CI, install and generation blocked in the app. See [Studio opt-out](LEGAL.md#studio-opt-out). | [opt-out](schemas/opt-out.schema.json) |
| [`policy/anti-cheat.json`](policy/anti-cheat.json) | Anti-cheat detection rules the app adds to its bundled list, games with an anti-cheat that leaves no files, and the whitelist of games that officially allow mods. Published in the index (`antiCheats`, per game `antiCheat` / `antiCheatAllowed`). See [Anti-cheat blocks](LEGAL.md#anti-cheat-blocks). | [anti-cheat](schemas/anti-cheat.schema.json) |
| [`policy/verified.json`](policy/verified.json) | Maintainer overrides of `verified`, see [Ratings and `verified`](#ratings-and-verified). | [verified-policy](schemas/verified-policy.schema.json) |

Issues use templates: [takedown request](https://github.com/ailocalpack/registry/issues/new?template=takedown.yml), [studio opt-out](https://github.com/ailocalpack/registry/issues/new?template=opt-out.yml), [wrong block](https://github.com/ailocalpack/registry/issues/new?template=block-report.yml); blank issues stay open for the app's *Report* link. What maintainers do with each: [LEGAL.md](LEGAL.md).

## License

Everything in this repository is licensed under [CC BY-SA 4.0](LICENSE). By opening a pull request you agree to license your contribution under it.
