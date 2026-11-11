# Legal: disclaimer, takedowns, opt-outs, blocks

## Disclaimer

Packs in this registry are fan translations made by players, often with the help of AI agents. They are not made, checked or endorsed by the games' developers or publishers, and they come **without any warranty**: a pack may be wrong, incomplete, or stop working after a game update. Installing one changes game files on your machine; the AI Local Pack app backs up every file it replaces and can uninstall the pack.

A pack holds translated text and instructions for rebuilding game files on the player's own machine from the player's own copy of the game: **no original game text, no game files, no programs.** A mod loader a pack needs (such as BepInEx) is downloaded by the app from its official release and checked against a hash the maintainers pinned ([`policy/dependencies.json`](policy/dependencies.json)).

Use packs only with copies of games you own. Packs made for pirated copies are not welcome here.

The registry's content is licensed under [CC BY-SA 4.0](LICENSE); by opening a pull request (or publishing from the app) you license your pack under it and confirm that you have the right to.

## Takedown requests

Rights holders who believe a pack infringes their rights can ask for its removal in two ways:

- **A public issue** with the [takedown template](https://github.com/ailocalpack/registry/issues/new?template=takedown.yml): which packs, which work, who you are, why.
- **GitHub's [DMCA takedown form](https://support.github.com/contact/dmca-takedown)**, when the details must stay private. GitHub hosts this repository and processes notices under its [DMCA Takedown Policy](https://docs.github.com/en/site-policy/content-removal-policies/dmca-takedown-policy); we follow GitHub's decision.

What the maintainers do with a takedown issue:

1. Acknowledge it within **7 days** and check that the request comes from the rights holder or their agent (an official website, a link from the store page, an e-mail domain). We may ask for more.
2. Remove the pack folders in a maintainer pull request (it says *Takedown* and links the issue), and delete the pack's patch archive from the `patches` release when it has one. The index is published again on merge, so the app stops listing the pack within minutes.
3. If the request asks for it, add the game to the opt-out list (see below), so no new pack for it is accepted.
4. Tell the pack's authors (by mentioning them in the issue). An author who thinks the removal is a mistake can reply there; under the DMCA, a formal counter notice goes through [GitHub's process](https://docs.github.com/en/site-policy/content-removal-policies/guide-to-submitting-a-dmca-counter-notice).

Removing a pack from the registry does not reach into players' machines: a copy someone already installed stays until they uninstall it.

## Studio opt-out

A studio or publisher that doesn't want fan translations of its game distributed here can opt the game out with an [opt-out issue](https://github.com/ailocalpack/registry/issues/new?template=opt-out.yml). We check that it comes from the studio (as for takedowns), then a maintainer adds the game to [`policy/opt-out.json`](policy/opt-out.json) with a note linking the issue ([schema](schemas/opt-out.schema.json)):

```json
{"schemaVersion": 1, "games": [
  {"game": "steam:620", "note": "requested by the publisher, #12"}
]}
```

From the next index build on:

- `index.json` marks the game `optOut` and lists none of its packs (they stay in git until a maintainer removes them);
- CI refuses new packs for it (`ailocalpack pack validate` reports the opt-out);
- the app blocks installing and generating packs for the game and explains why; the app's *Publish* refuses it too.

An opt-out covers the whole game, every language. To lift it, the studio comments on the issue or opens a new one, and a maintainer removes the entry.

## Anti-cheat blocks

The app refuses to install or generate packs for games with an anti-cheat (Easy Anti-Cheat, BattlEye, Vanguard, ...): changing their files can get players banned. It finds an anti-cheat by its files in the game folder (a list bundled with the app) and by the registry's [`policy/anti-cheat.json`](policy/anti-cheat.json) ([schema](schemas/anti-cheat.schema.json)), which the index publishes so the app learns about new anti-cheats without an update:

```json
{"schemaVersion": 1,
 "antiCheats": [{"id": "acme-guard", "name": "Acme Guard", "markers": ["AcmeGuard/", "acme*.sys"]}],
 "games": [{"game": "steam:730", "antiCheat": "vanguard"}],
 "allowed": [{"game": "steam:570", "note": "the studio allows mods: <link to the statement>"}]}
```

- `antiCheats`: detection rules. A rule with the ID of a bundled one replaces it; a new ID adds an anti-cheat. Markers are file or folder names (`EasyAntiCheat/` for a folder), or short paths (`pb/pbcl.dll`), `*` / `?` only in the last part; the app checks every game again when the rules change.
- `games`: games that use an anti-cheat leaving no files in the game folder (kernel anti-cheats installed elsewhere). The anti-cheat is one of the rules here or of the app's bundled list (`eac`, `battleye`, `vanguard`, `gameguard`, `xigncode`, `punkbuster`, `mhyprot`).
- `allowed`: games that officially allow mods. They are never blocked for an anti-cheat, whatever was found; an opt-out still blocks them. The note links the studio's statement.

If the app blocks a game it shouldn't (or misses an anti-cheat), use the **Report** link on the game's page in the app, or the [block report template](https://github.com/ailocalpack/registry/issues/new?template=block-report.yml). Changes to the policy files are maintainer pull requests; a broken file stops the index build, so the published index never drops a block by accident.
