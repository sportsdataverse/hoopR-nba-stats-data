#!/bin/bash
while getopts s:e:r: flag
do
    case "${flag}" in
        s) START_YEAR=${OPTARG};;
        e) END_YEAR=${OPTARG};;
        r) RESCRAPE=${OPTARG};;
    esac
done

# run_and_commit <commit-season> <Rscript> [args...]
# Run one scraper, then commit + push its output on its own so a later
# slow/hung script (the per-game pbp scrape, especially on an empty cache,
# can run for a long time) can no longer block earlier output from landing --
# the previous single end-of-loop commit lost everything if pbp stalled.
# The "(Start: Y End: Y)" subject is load-bearing for downstream year parsing.
run_and_commit() {
    local season="$1"; shift
    Rscript "$@"
    git pull >> /dev/null 2>&1 || true
    git add nba_stats/* . >> /dev/null 2>&1 || true
    git commit -m "NBA Stats Update (Start: ${season} End: ${season})" >> /dev/null 2>&1 \
        || echo "No changes to commit for $2"
    git pull --rebase >> /dev/null 2>&1 || true
    git push >> /dev/null 2>&1 || true
}

for i in $(seq "${START_YEAR}" "${END_YEAR}")
do
    echo "$i"
    git config --local user.email "action@github.com"
    git config --local user.name "Github Action"
    # Schedules first (light) -- commits independently.
    run_and_commit "$i" R/nba_stats_01_scrape_schedules.R -s $i -e $i -r $RESCRAPE
    # Heavy per-game pbp last -- a slow / empty-cache pbp pass can no longer
    # block the schedule output above from committing.
    run_and_commit "$i" R/nba_stats_02_scrape_pbp.R -s $i -e $i -r $RESCRAPE
done
