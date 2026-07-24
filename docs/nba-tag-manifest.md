# NBA Stats v3 reshaper — tag manifest (Phase 0, Task 0.1)

Cross-checks the 15 target `nba_stats_*` release tags against what is live on
`sportsdataverse/sportsdataverse-data` today, and records the one retirement.

- **Source of truth:** `gh release list --repo sportsdataverse/sportsdataverse-data --limit 300`
  (run 2026-07-23; `gh` authed as `saiemgilani`).
- Season labels are start-year throughout (matches the existing `nba_stats_leaguedash`
  asset filenames, which use start years, e.g. `standings_2013.parquet`).

## Live `nba_stats_*` tags today (8)

| tag | created | in target 15? | disposition |
|---|---|---|---|
| `nba_stats_schedules` | 2023-03-30 | yes | **REBUILD** |
| `nba_stats_pbp` | 2023-03-30 | yes | **REBUILD** |
| `nba_stats_player_boxscores` | 2023-03-30 | yes | **REBUILD** |
| `nba_stats_team_boxscores` | 2023-03-30 | yes | **REBUILD** |
| `nba_stats_pbpv3` | 2026-07-03 | no | **RETIRE** (after `nba_stats_pbp` rebuilt + verified) |
| `nba_stats_leaguedash` | 2026-06-24 | no (legacy combined) | **LEAVE** (not fully superseded — see below) |
| `nba_stats_possessions_v3` | 2026-07-03 | no | **LEAVE** (no classic twin) |
| `nba_stats_lineups_v3` | 2026-07-03 | no | **LEAVE** (no classic twin; ≠ `nba_stats_lineups`) |

## The 15 target tags → action

| # | dataset key | tag | source endpoint | action |
|---|---|---|---|---|
| 1 | standings | `nba_stats_standings` | leaguestandingsv3 | **CREATE** |
| 2 | player_season_stats | `nba_stats_player_season_stats` | leaguedashplayerstats | **CREATE** |
| 3 | team_season_stats | `nba_stats_team_season_stats` | leaguedashteamstats | **CREATE** |
| 4 | lineups | `nba_stats_lineups` | leaguedashlineups | **CREATE** |
| 5 | rosters | `nba_stats_rosters` | commonteamroster | **CREATE** |
| 6 | coaches | `nba_stats_coaches` | commonteamroster | **CREATE** |
| 7 | draft | `nba_stats_draft` | drafthistory | **CREATE** (blocked on Phase 3 capture) |
| 8 | schedules | `nba_stats_schedules` | leaguegamelog | **REBUILD** |
| 9 | player_game_logs | `nba_stats_player_game_logs` | leaguegamelog | **CREATE** |
| 10 | pbp | `nba_stats_pbp` | playbyplayv3 | **REBUILD** |
| 11 | game_rosters | `nba_stats_game_rosters` | boxscoresummaryv2 | **CREATE** |
| 12 | officials | `nba_stats_officials` | boxscoresummaryv2 | **CREATE** |
| 13 | player_boxscores | `nba_stats_player_boxscores` | boxscoretraditionalv3 | **REBUILD** |
| 14 | team_boxscores | `nba_stats_team_boxscores` | boxscoretraditionalv3 | **REBUILD** |
| 15 | shots | `nba_stats_shots` | derived from playbyplayv3 | **CREATE** |

**Tally:** 11 CREATE, 4 REBUILD (schedules, pbp, player_boxscores, team_boxscores), 0
decision-needed. `upload_artifacts` in `publish.py` already `--clobber`s and creates missing
releases, so CREATE vs REBUILD is the same publish call — the distinction is only about what
existing content is overwritten.

## `nba_stats_leaguedash` disposition — LEAVE (do not fold/delete)

`gh release view nba_stats_leaguedash --json assets`: **794 assets**, created 2026-06-24,
start-year filenames. It is a broad *combined legacy dump* spanning these families (one
`{family}_{startyear}.{ext}` set each):

```
standings                                            <- overlaps new nba_stats_standings
player_stats_{base,advanced,defense,misc,scoring,usage}   <- overlaps new nba_stats_player_season_stats
team_stats_{base,advanced,defense,fourfactors,misc,opponent,scoring}  <- overlaps new nba_stats_team_season_stats
lineups_{base,advanced,fourfactors,misc,opponent,scoring,master}      <- overlaps new nba_stats_lineups
player_bio                                           <- NOT covered by the 15 (leaguedashplayerbiostats)
player_tracking_{catchshoot,defense,drives,efficiency,elbowtouch,painttouch,
                 passing,possessions,posttouch,pullupshot,rebounding,speeddistance}  <- NOT covered (leaguedashptstats)
{player,team}_master                                 <- rollup convenience files, NOT covered
```

**Decision: LEAVE it in place.** The three new split datasets
(`player_season_stats` / `team_season_stats` / `lineups`) plus `standings` supersede only
the `player_stats_*` / `team_stats_*` / `lineups_*` / `standings` families. `leaguedash`
additionally carries `player_bio`, the twelve `player_tracking_*` families, and the
`*_master` rollups, none of which are in the target 15 — so the split datasets do **not**
fully replace it. Folding/deleting would drop live content. The new tags coexist with it.
(Revisiting `nba_stats_leaguedash` — porting player_bio / player_tracking / masters — is
out of scope for this port; note it as future work if those families are still wanted.)

## Retirement — `nba_stats_pbpv3`

- `nba_stats_pbpv3` (created 2026-07-03) is the redundant v3 pbp tag folded into
  `nba_stats_pbp` by this port.
- **Retire only after** `nba_stats_pbp` is rebuilt from `playbyplayv3` and verified
  (Phase 5.3): `gh release delete nba_stats_pbpv3 --repo sportsdataverse/sportsdataverse-data`.
- Do **not** touch `nba_stats_possessions_v3` or `nba_stats_lineups_v3` — they have no
  classic twin. In particular `nba_stats_lineups_v3` (on-court possession lineups) is a
  different dataset from the new `nba_stats_lineups` (leaguedash lineups); do not conflate.
