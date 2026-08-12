#!/usr/bin/env bash
# Create the GitHub releases on sportsdataverse/sportsdataverse-data that this
# repo's builders upload artifacts to. Each release is created with an empty
# asset list; the data lands later during the daily/weekly processor runs.
#
# Source-specific: this repo (hoopR-nba-stats-data) owns the `nba_stats_*` tags.
# The sister init script in wehoop-wnba-stats-data owns the `wnba_stats_*` ones.
#
# WHY THIS EXISTS: `gh release upload` (and piggyback::pb_upload) cannot CREATE a
# release -- it fails on a nonexistent tag. Worse, the v3 cutover's dry run cannot
# warn you, because `remote_assets()` returns {} for both "release absent" and
# "release exists but is empty". So a publish into an unprovisioned tag dies
# mid-upload. Run this first whenever the pipeline gains a new release target.
#
# Idempotent: a release that already exists is skipped, not re-created, and no
# existing release's assets, body, or timestamps are touched.
#
# Usage: bash ops/init/0000_create_hoopr_nba_stats_releases_init.sh

set -euo pipefail

REPO="sportsdataverse/sportsdataverse-data"

create_release() {
  local tag="$1" body="$2"
  if gh release view "$tag" --repo "$REPO" >/dev/null 2>&1; then
    echo "Skipping (already exists): $tag"
    return 0
  fi
  gh release create "$tag" --repo "$REPO" --target main --title "$tag" --notes "$body"
}

#--- NBA Stats (stats.nba.com) -----------------------------------------------

# The 15 reshaper tags -- one per entry in `nba_data_build.reshape.datasets.DATASETS`.
create_release "nba_stats_schedules"           "NBA Schedules Data (from stats.nba.com)"
create_release "nba_stats_pbp"                 "NBA Play-by-Play Data (from stats.nba.com)"
create_release "nba_stats_team_boxscores"      "NBA Team Boxscores Data (from stats.nba.com)"
create_release "nba_stats_player_boxscores"    "NBA Player Boxscores Data (from stats.nba.com)"
create_release "nba_stats_standings"           "NBA Standings Data (from stats.nba.com)"
create_release "nba_stats_player_season_stats" "NBA Player Season Stats Data (from stats.nba.com)"
create_release "nba_stats_team_season_stats"   "NBA Team Season Stats Data (from stats.nba.com)"
create_release "nba_stats_lineups"             "NBA Lineups Data (from stats.nba.com)"
create_release "nba_stats_rosters"             "NBA Team Rosters Data (from stats.nba.com)"
create_release "nba_stats_coaches"             "NBA Coaches Data (from stats.nba.com)"
create_release "nba_stats_draft"               "NBA Draft Data (from stats.nba.com)"
create_release "nba_stats_player_game_logs"    "NBA Player Game Logs Data (from stats.nba.com)"
create_release "nba_stats_game_rosters"        "NBA Game Rosters Data (from stats.nba.com)"
create_release "nba_stats_officials"           "NBA Officials Data (from stats.nba.com)"
create_release "nba_stats_shots"               "NBA Shots Data (from stats.nba.com)"

# Program V (D26d) cutover targets -- the two `v3_cutover.TARGETS` tags that the
# reshaper inventory above does not already provision. `nba_stats_game_lineups`
# is the PER-GAME lineups dataset and is deliberately NOT `nba_stats_lineups`
# above, which carries the season-level leaguedashlineups dataset -- a different
# dataset, not an older version of this one.
create_release "nba_stats_possessions"         "NBA Possessions Data (from stats.nba.com)"
create_release "nba_stats_game_lineups"        "NBA Per-Game Lineups Data (from stats.nba.com)"
