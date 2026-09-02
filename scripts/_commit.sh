#!/usr/bin/env bash
# Commit + push, surviving a remote that moved while the build was running.
# Source it, do not execute:
#
#     source "$(dirname "${BASH_SOURCE[0]}")/_commit.sh"
#     sdv_commit_push "NBA Player Impact Update (Start: 2026 End: 2026)" nba_stats/player_impact
#
# Byte-sibling of wehoop-wnba-stats-data/scripts/_commit.sh and
# cfbfastR-cfb-raw/scripts/_commit.sh -- change all three together (the twin
# rule). This function encodes two incidents, and a drifted copy loses them.
#
# Pulling BEFORE staging can only abort: the build has just rewritten tracked
# parquet, so `git pull` refuses with "Your local changes would be overwritten
# by merge". The old form committed anyway, pushed into a non-fast-forward
# rejection, and swallowed it -- a GREEN job that published nothing (hoopR-nba-
# data run 32204419012, wehoop-wnba-data 32192069433/32192069566).
#
# Stage and commit FIRST so the tree is clean, then reconcile. `rebase --merge`
# rather than `pull --rebase`: the default am backend base64-encodes every blob
# it replays, which crawls on a repo carrying parquet.
sdv_commit_push() {
  local msg="$1"; shift
  git add -- "$@" >/dev/null 2>&1 || true
  if git diff --cached --quiet; then
    echo "nothing to commit for: $msg"
    return 0
  fi
  git commit -m "$msg" >/dev/null || { echo "::warning ::commit failed: $msg"; return 1; }
  local attempt
  for attempt in 1 2 3; do
    if git push origin HEAD >/dev/null 2>&1; then
      echo "pushed: $msg (attempt $attempt)"
      return 0
    fi
    echo "push rejected (attempt $attempt); syncing with origin"
    git fetch --quiet origin main || true
    if ! git rebase --merge origin/main >/dev/null 2>&1; then
      git rebase --abort >/dev/null 2>&1 || true
      echo "::error ::cannot rebase onto origin/main for: $msg"
      return 1
    fi
  done
  echo "::error ::push still rejected after 3 attempts: $msg"
  return 1
}
