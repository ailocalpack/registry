# ailocalpack registry

Community localizations ("packs") for games, installed with the [ailocalpack](https://github.com/ailocalpack/ailocalpack) app.
The app reads one file, [`index.json`](https://ailocalpack.github.io/registry/index.json), published from this repository to GitHub Pages, and downloads only the packs a player installs.

> **Disclaimer.** Packs are fan translations made by players, often with the help of AI agents. They are not made, checked or endorsed by the games' developers or publishers, and come without any warranty. A pack holds translated text and instructions for rebuilding game files on the player's machine: **no original game text, no game files, no programs**. Use packs only with copies of games you own. Rights holders who want a pack removed, or no packs for their game at all, can open an issue (the takedown and opt-out process is being written down; until then an issue reaches the maintainers).

## Layout

```
games/<game folder>/<language>/<pack-id>/
  manifest.json            what the pack is, which game builds it fits, how to apply it
  strings/strings.json.gz  the translations (gzip'd JSON string table)
schemas/                   JSON Schemas of manifest.json, the string table and index.json
policy/                    lists the app relies on (anti-cheat whitelist, opt-outs); maintainers only
ci/ailocalpack-ref         the ailocalpack commit CI builds its CLI from
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

Check it locally with the CLI (built from the commit in [`ci/ailocalpack-ref`](ci/ailocalpack-ref)):

```sh
ailocalpack pack validate games/<game folder>/<language>/<pack-id>
ailocalpack index build . --out /tmp/index.json
```

## What CI does

| Workflow | When | What |
| --- | --- | --- |
| [Validate](.github/workflows/validate.yml) | every pull request | Builds the CLI, checks the pull request changes one pack folder (others: maintainers only), the pack is `alpha`, `ailocalpack pack validate` passes (manifest and string table formats, hashes and sizes, folder layout, size limits, **no executable files** by extension or by content), `schemas/` matches the CLI's, the index still builds. Problems show up as annotations on the files. |
| [Auto-merge](.github/workflows/auto-merge.yml) | after Validate passes | From `main`'s copy of the checks: reads the changed files from the GitHub API, repeats the one-folder, `alpha` and validation checks on the pull request's head commit, squash-merges it and starts Publish. Pull requests that change anything else wait for a maintainer. |
| [Publish index](.github/workflows/publish.yml) | push to `main`, after a merge, by hand | `ailocalpack index build`, then publishes `index.json`, `games/` and `schemas/` to <https://ailocalpack.github.io/registry/>. |

The CLI is built from source at the pinned commit until the app ships releases; then CI downloads the released binary (pinned version and hash). To move the pin, change `ci/ailocalpack-ref` (and copy the new `schemas/` if they changed) in a maintainer pull request.

### Checking CI by hand

The workflows are tested with these pull requests whenever they change (open them from a fork, so the fork path is covered):

| Pull request | Expected |
| --- | --- |
| A copy of the sample pack under a new `<pack-id>` (folder and `id` renamed, `revision` 1) | Validate passes, Auto-merge merges it, Publish runs, `index.json` lists the new pack within minutes. Remove it afterwards in a maintainer pull request. |
| The same, plus a file `strings/tool.exe` (any content) | Validate fails: `strings/tool.exe` *has an executable, script or archive extension*. Not merged. |
| The same, with an ELF or `MZ` header saved as `strings/extra.json` | Validate fails: `strings/extra.json` *is a Windows executable (PE)* / *Linux executable (ELF)*. Not merged. |
| A pack with `"status": "verified"` | Validate fails on `status`. Not merged. |
| A pack plus a change to `README.md` | Validate fails for a contributor ("one pack per pull request"); for a maintainer it passes and waits for review. |
| A wrong `strings.sha256` in the manifest | Validate fails on `strings.sha256`. Not merged. |

## Sample pack

[`games/fp-f362…0288/ru/sample-quest-ru`](games/fp-f362498e21ee992e45352516246500dac24e10b902c54cba2a144c51fe040288/ru/sample-quest-ru) is a Russian pack for *Sample Quest*, a synthetic RPG Maker MZ game that lives in the app repository as [`tests/fixtures/games/sample-quest`](https://github.com/ailocalpack/ailocalpack/tree/master/tests/fixtures/games/sample-quest) (a few text files, nothing to run). Add that folder to the app's library and the pack shows up for it.

## License

Everything in this repository is licensed under [CC BY-SA 4.0](LICENSE). By opening a pull request you agree to license your contribution under it.
