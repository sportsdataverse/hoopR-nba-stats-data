#!/usr/bin/env bash
# Hydrate a local raw-JSON store from hoopR-nba-stats-raw's per-season bundles.
#
# The clone-free way to run a FULL-history impact build in CI. Reading the raw
# repo per-file over URL is right for an incremental refresh, but a 1997:2026
# rebuild touches ~120k files; this pulls ~30 release tarballs instead and
# extracts them into one directory that is a valid raw store root. Cloning the
# ~1GB raw repo is never necessary.
#
#   bash scripts/hydrate_raw_store.sh                     # 1996:2026 -> ./.raw_store
#   bash scripts/hydrate_raw_store.sh 2024:2026           # a sub-range
#   RAW_STORE_DIR=/data/raw bash scripts/hydrate_raw_store.sh
#
# Then point the build at it (no proxy, no live stats.nba.com):
#   python -m nba_model_publish impact --seasons 1997:2026 --raw-store-dir "$RAW_STORE_DIR"
#
# Idempotent + resumable: a season whose bundle already extracted is skipped, so
# a killed run can be re-run. Requires `gh` (read access is enough).
set -uo pipefail

SEASONS="${1:-1996:2026}"
REPO="${RAW_REPO:-sportsdataverse/hoopR-nba-stats-raw}"
TAG="${BUNDLE_TAG:-nba-stats-raw-json}"
DEST="${RAW_STORE_DIR:-$PWD/.raw_store}"
TMP="${BUNDLE_TMP_DIR:-$DEST/.bundles}"

command -v gh >/dev/null || { echo "FATAL: gh CLI not found" >&2; exit 3; }
mkdir -p "$DEST" "$TMP" || { echo "FATAL: cannot create $DEST" >&2; exit 1; }

lo="${SEASONS%%:*}"; hi="${SEASONS##*:}"
ok=0; missing=0; failed=0

for season in $(seq "$lo" "$hi"); do
  # A season is already hydrated if any endpoint dir for it exists. Marker file
  # rather than a content check: bundles are whole-season, so partial extraction
  # is the only failure mode and it re-runs cleanly.
  marker="$DEST/.hydrated_$season"
  if [ -f "$marker" ]; then
    echo "season $season: already hydrated, skipping"; ok=$((ok + 1)); continue
  fi
  asset="nba_stats_json_${season}.tar.gz"
  if ! gh release download "$TAG" --repo "$REPO" --pattern "$asset" --dir "$TMP" --clobber 2>/dev/null; then
    echo "season $season: no bundle published ($asset)"; missing=$((missing + 1)); continue
  fi
  # Archive paths are store-relative ({endpoint}/{season}/...), so every season
  # extracts into the SAME root and the result is a complete store.
  if tar -xzf "$TMP/$asset" -C "$DEST"; then
    touch "$marker"; rm -f "$TMP/$asset"
    echo "season $season: hydrated"
    ok=$((ok + 1))
  else
    echo "season $season: EXTRACT FAILED" >&2
    failed=$((failed + 1))
  fi
done

# A torn extraction leaves a PARTIAL season on disk, and the store's read path
# treats a missing file as an ordinary miss -- so exiting 0 here would let a
# build proceed against silently-incomplete data. Fail loudly instead.
if [ "$failed" -gt 0 ]; then
  echo "FATAL: $failed season(s) failed to extract -- store at $DEST is INCOMPLETE." >&2
  echo "       Delete the affected .hydrated_<season> marker(s) and re-run." >&2
  exit 5
fi

echo "store ready: $DEST ($ok season(s) present, $missing bundle(s) unpublished)"
echo "  use: python -m nba_model_publish impact --seasons ${lo}:${hi} --raw-store-dir \"$DEST\""
