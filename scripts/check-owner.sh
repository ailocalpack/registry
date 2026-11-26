#!/usr/bin/env bash
# Whose pack a pack pull request touches, and whether its authors let it in.
#
#   scripts/check-owner.sh <pack folder> <base root> <pull request author> <reviews.json> <head sha>
#
# <pack folder> is the pull request's copy (games/<game>/<language>/<pack-id>, under any root); <base root> a checkout
# of master, where the merged pack is <base root>/games/<game>/<language>/<pack-id>; <reviews.json> GitHub's list of
# the pull request's reviews (GET /repos/.../pulls/<n>/reviews, oldest first; "[]" when unknown).
#
# A new pack is its author's: the manifest's first author must be the pull request's author, else it fails. A revision
# of a merged pack by one of its authors goes in. A revision by anyone else waits for the merged pack's authors: one
# of them approves the pull request's head commit (an APPROVED review on <head sha>), or asks for changes, and then a
# maintainer decides. An author's latest review counts; a dismissed one counts for nothing.
#
# Prints GITHUB_OUTPUT lines:
#   owner=ok        merge (a new pack, the author's own revision, or an approved one)
#   owner=wait      no author has approved the head commit yet
#   owner=declined  an author asked for changes
#   authors=<logins>  the merged pack's authors, space-separated (for owner=wait / declined)
# Exits 1 with an annotation when the pack can't be read or a new pack names someone else first.
set -euo pipefail

pack="${1:?usage: check-owner.sh <pack folder> <base root> <pr author> <reviews.json> <head sha>}"
base="${2:?base root}"
author="${3:?pull request author}"
reviews="${4:?reviews.json}"
head="${5:?head sha}"

manifest="$pack/manifest.json"
if [[ -L "$manifest" || ! -f "$manifest" ]]; then
  echo "::error file=$manifest,title=manifest.json::must be a plain file"
  exit 1
fi

# The folder inside games/ (the same path under the base root).
if [[ ! "$pack" =~ (games/[^/]+/[^/]+/[^/]+)/?$ ]]; then
  echo "::error file=$manifest,title=authors::not a pack folder (games/<game>/<language>/<pack-id>)"
  exit 1
fi
merged="$base/${BASH_REMATCH[1]}/manifest.json"
lower="$(printf '%s' "$author" | tr '[:upper:]' '[:lower:]')"

if [[ ! -f "$merged" ]]; then
  first="$(jq -r '.authors[0].github // empty | ascii_downcase' "$manifest" 2>/dev/null || true)"
  if [[ "$first" != "$lower" ]]; then
    echo "::error file=$manifest,title=authors::a new pack's first author must be whoever opens the pull request ($author), not \"${first:-none}\"; to change someone else's pack, publish a new revision of it"
    exit 1
  fi
  echo "owner=ok"
  exit 0
fi

authors="$(jq -r '[.authors[].github] | join(" ")' "$merged")"
if jq -e --arg who "$lower" 'any(.authors[]; (.github | ascii_downcase) == $who)' "$merged" > /dev/null; then
  echo "owner=ok"
  exit 0
fi

# Each merged author's latest review that decides something (APPROVED, CHANGES_REQUESTED, DISMISSED).
state="$(jq -r --slurpfile m "$merged" --arg head "$head" '
  ($m[0].authors | map(.github | ascii_downcase)) as $authors
  | [ .[] | select(.user.login != null and .state != "COMMENTED" and .state != "PENDING")
          | select((.user.login | ascii_downcase) as $u | $authors | index($u)) ]
  | group_by(.user.login | ascii_downcase)
  | map(last)
  | if any(.[]; .state == "CHANGES_REQUESTED") then "declined"
    elif any(.[]; .state == "APPROVED" and .commit_id == $head) then "ok"
    else "wait" end' "$reviews")"

echo "owner=$state"
echo "authors=$authors"
