# NBA player impact — the six-engine suite


The consolidated player-impact suite publishes one row per player-season
(regular season and playoffs) on the `nba_player_impact` release tag,
with six engines’ columns side by side:

| engine | what it contributes |
|----|----|
| RAPM | possession on/off ridge (`o_rapm` / `d_rapm` / `rapm`) |
| adj-RAPM | RAPM with an SPM-derived prior (previous season’s RS+PO blend) |
| SPM | box-score plus/minus, coefficients fit on RS RAPM targets |
| BPM 2.0 | box logs + listed positions (`obpm` / `dbpm` / `bpm`) |
| DARKO-style | cross-season Kalman filter + aging curve (projects next season) |
| WAR | RAPM rating × calibrated pts-per-win, replacement level −2.0 |

Seasons build earliest-to-latest because two engines carry state
forward: SPM coefficients are fit ONCE per season on regular-season RAPM
(a ~15-game playoff sample would train noise on noise), and adj-RAPM’s
prior is the *previous* season’s possession-weighted RS+PO SPM blend — a
gap season deliberately breaks the prior chain. DARKO runs a per-season
Kalman step over the RAPM panel with an aging curve; playoff form enters
as a possession-weighted blend rather than a second time step, because a
second step would apply a season of aging twice.

The substrate is the committed `hoopR-nba-stats-raw` store (per-game
playbyplay / rotation / boxscore payloads plus season-level captures),
read offline through the raw-store backend — `readonly` means OFFLINE: a
store miss raises rather than silently completing over the network, so a
build is reproducible or loudly incomplete, never quietly mixed. This
document, by contrast, evaluates the **published releases**: every
number and figure below is recomputed at render time from the release
assets themselves, which is exactly what a consumer downloads.

## Training data

<div id="smvvdpxvsp" style="padding-left:0px;padding-right:0px;padding-top:10px;padding-bottom:10px;overflow-x:auto;overflow-y:auto;width:auto;height:auto;">
<style>
#smvvdpxvsp table {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', 'Fira Sans', 'Droid Sans', Arial, sans-serif;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }
&#10;#smvvdpxvsp thead, tbody, tfoot, tr, td, th { border-style: none; }
 tr { background-color: transparent; }
#smvvdpxvsp p { margin: 0; padding: 0; }
 #smvvdpxvsp .gt_table { display: table; border-collapse: collapse; line-height: normal; margin-left: auto; margin-right: auto; color: #333333; font-size: 16px; font-weight: normal; font-style: normal; background-color: #FFFFFF; width: auto; border-top-style: solid; border-top-width: 2px; border-top-color: #A8A8A8; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #A8A8A8; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; }
 #smvvdpxvsp .gt_caption { padding-top: 4px; padding-bottom: 4px; }
 #smvvdpxvsp .gt_title { color: #333333; font-size: 125%; font-weight: initial; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; border-bottom-color: #FFFFFF; border-bottom-width: 0; }
 #smvvdpxvsp .gt_subtitle { color: #333333; font-size: 85%; font-weight: initial; padding-top: 3px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; border-top-color: #FFFFFF; border-top-width: 0; }
 #smvvdpxvsp .gt_heading { background-color: #FFFFFF; text-align: center; border-bottom-color: #FFFFFF; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #smvvdpxvsp .gt_bottom_border { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #smvvdpxvsp .gt_col_headings { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #smvvdpxvsp .gt_col_heading { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; overflow-x: hidden; }
 #smvvdpxvsp .gt_column_spanner_outer { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; padding-top: 0; padding-bottom: 0; padding-left: 4px; padding-right: 4px; }
 #smvvdpxvsp .gt_column_spanner_outer:first-child { padding-left: 0; }
 #smvvdpxvsp .gt_column_spanner_outer:last-child { padding-right: 0; }
 #smvvdpxvsp .gt_column_spanner { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; overflow-x: hidden; display: inline-block; width: 100%; }
 #smvvdpxvsp .gt_spanner_row { border-bottom-style: hidden; }
 #smvvdpxvsp .gt_group_heading { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; text-align: left; }
 #smvvdpxvsp .gt_empty_group_heading { padding: 0.5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: middle; }
 #smvvdpxvsp .gt_from_md> :first-child { margin-top: 0; }
 #smvvdpxvsp .gt_from_md> :last-child { margin-bottom: 0; }
 #smvvdpxvsp .gt_row { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; margin: 10px; border-top-style: solid; border-top-width: 1px; border-top-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; overflow-x: hidden; }
 #smvvdpxvsp .gt_stub { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; }
 #smvvdpxvsp .gt_indent_1 { text-indent: 5px; }
 #smvvdpxvsp .gt_indent_2 { text-indent: calc(5px * 2); }
 #smvvdpxvsp .gt_indent_3 { text-indent: calc(5px * 3); }
 #smvvdpxvsp .gt_indent_4 { text-indent: calc(5px * 4); }
 #smvvdpxvsp .gt_indent_5 { text-indent: calc(5px * 5); }
 #smvvdpxvsp .gt_stub_row_group { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; vertical-align: top; }
 #smvvdpxvsp .gt_row_group_first td { border-top-width: 2px; }
 #smvvdpxvsp .gt_row_group_first th { border-top-width: 2px; }
 #smvvdpxvsp .gt_striped { color: #333333; background-color: #F4F4F4; }
 #smvvdpxvsp .gt_table_body { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #smvvdpxvsp .gt_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #smvvdpxvsp .gt_first_summary_row { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; }
 #smvvdpxvsp .gt_last_summary_row_top { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #smvvdpxvsp .gt_grand_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #smvvdpxvsp .gt_first_grand_summary_row_bottom { border-top-style: double; border-top-width: 6px; border-top-color: #D3D3D3; }
 #smvvdpxvsp .gt_last_grand_summary_row_top { border-bottom-style: double; border-bottom-width: 6px; border-bottom-color: #D3D3D3; }
 #smvvdpxvsp .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #smvvdpxvsp .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #smvvdpxvsp .gt_left { text-align: left; }
 #smvvdpxvsp .gt_center { text-align: center; }
 #smvvdpxvsp .gt_right { text-align: right; font-variant-numeric: tabular-nums; }
 #smvvdpxvsp .gt_font_normal { font-weight: normal; }
 #smvvdpxvsp .gt_font_bold { font-weight: bold; }
 #smvvdpxvsp .gt_font_italic { font-style: italic; }
 #smvvdpxvsp .gt_super { font-size: 65%; }
 #smvvdpxvsp .gt_footnotes { color: font-color(#FFFFFF); background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #smvvdpxvsp .gt_footnote { margin: 0px; font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; }
 #smvvdpxvsp .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #smvvdpxvsp .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #smvvdpxvsp .gt_footnote_marks { font-size: 75%; vertical-align: 0.4em; position: initial; }
 #smvvdpxvsp .gt_asterisk { font-size: 100%; vertical-align: 0; }
 &#10;</style>

| Published nba_player_impact assets — last 12 of 30 seasons (1997–2026) |  |  |  |
|----|----|----|----|
| one row per player-season-seasontype; computed at render time from the release |  |  |  |
| season | player_rows | playoff_rows | off_possessions |
| 2015 | 700 | 208 | 1,244,400 |
| 2016 | 691 | 215 | 1,268,870 |
| 2017 | 701 | 215 | 1,267,830 |
| 2018 | 752 | 210 | 1,275,365 |
| 2019 | 742 | 212 | 1,312,800 |
| 2020 | 744 | 215 | 1,145,775 |
| 2021 | 779 | 239 | 1,153,500 |
| 2022 | 820 | 215 | 1,291,255 |
| 2023 | 756 | 217 | 1,303,355 |
| 2024 | 786 | 214 | 1,289,125 |
| 2025 | 788 | 219 | 1,299,230 |
| 2026 | 812 | 230 | 1,309,825 |

&#10;</div>

## Exploratory data analysis

<img src="player_impact_files/figure-commonmark/cell-4-output-1.png"
width="420" height="300"
alt="Engine distributions, latest regular season — all engines center near zero on the per-100 scale except WAR (a counting stat)." />

<img src="player_impact_files/figure-commonmark/cell-5-output-1.png"
width="420" height="300"
alt="Cross-engine agreement, latest regular season (Pearson r) — engines measure related but distinct things." />

The correlation matrix is the suite’s honesty check: RAPM and adj-RAPM
agree strongly (the prior stabilizes, it does not overwrite), box
engines (SPM, BPM) form their own cluster, and DARKO’s filtered skill —
which sees every prior season — correlates with everything while
duplicating nothing.

## Attribution

The engines are linear models (ridge, regression, Kalman), so
attribution is native: each engine’s O/D split *is* its decomposition,
and the published columns carry it (`o_rapm`/`d_rapm`, `ospm`/`dspm`,
`obpm`/`dbpm`, `o_adj_rapm`/`d_adj_rapm`). No SHAP approximation is
needed — the columns are the exact attributions. What the release does
*not* carry is the SPM coefficient vector itself (it lives in the build
artifacts under `build_out/impact_engines/`), an omission recorded in
the avenues below.

<img src="player_impact_files/figure-commonmark/cell-6-output-1.png"
width="420" height="300"
alt="adj-RAPM vs RAPM, latest regular season — the SPM prior shrinks, it does not overwrite." />

## Evaluation

**DARKO forward validation** is the suite’s headline out-of-sample test:
the projection made in season t (`darko_projected_rating`, which sees
nothing after t) against the realized RAPM in season t+1. Recomputed at
render time over every adjacent published season pair:

<div id="xgmntcxysw" style="padding-left:0px;padding-right:0px;padding-top:10px;padding-bottom:10px;overflow-x:auto;overflow-y:auto;width:auto;height:auto;">
<style>
#xgmntcxysw table {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', 'Fira Sans', 'Droid Sans', Arial, sans-serif;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }
&#10;#xgmntcxysw thead, tbody, tfoot, tr, td, th { border-style: none; }
 tr { background-color: transparent; }
#xgmntcxysw p { margin: 0; padding: 0; }
 #xgmntcxysw .gt_table { display: table; border-collapse: collapse; line-height: normal; margin-left: auto; margin-right: auto; color: #333333; font-size: 16px; font-weight: normal; font-style: normal; background-color: #FFFFFF; width: auto; border-top-style: solid; border-top-width: 2px; border-top-color: #A8A8A8; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #A8A8A8; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; }
 #xgmntcxysw .gt_caption { padding-top: 4px; padding-bottom: 4px; }
 #xgmntcxysw .gt_title { color: #333333; font-size: 125%; font-weight: initial; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; border-bottom-color: #FFFFFF; border-bottom-width: 0; }
 #xgmntcxysw .gt_subtitle { color: #333333; font-size: 85%; font-weight: initial; padding-top: 3px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; border-top-color: #FFFFFF; border-top-width: 0; }
 #xgmntcxysw .gt_heading { background-color: #FFFFFF; text-align: center; border-bottom-color: #FFFFFF; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #xgmntcxysw .gt_bottom_border { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #xgmntcxysw .gt_col_headings { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #xgmntcxysw .gt_col_heading { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; overflow-x: hidden; }
 #xgmntcxysw .gt_column_spanner_outer { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; padding-top: 0; padding-bottom: 0; padding-left: 4px; padding-right: 4px; }
 #xgmntcxysw .gt_column_spanner_outer:first-child { padding-left: 0; }
 #xgmntcxysw .gt_column_spanner_outer:last-child { padding-right: 0; }
 #xgmntcxysw .gt_column_spanner { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; overflow-x: hidden; display: inline-block; width: 100%; }
 #xgmntcxysw .gt_spanner_row { border-bottom-style: hidden; }
 #xgmntcxysw .gt_group_heading { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; text-align: left; }
 #xgmntcxysw .gt_empty_group_heading { padding: 0.5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: middle; }
 #xgmntcxysw .gt_from_md> :first-child { margin-top: 0; }
 #xgmntcxysw .gt_from_md> :last-child { margin-bottom: 0; }
 #xgmntcxysw .gt_row { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; margin: 10px; border-top-style: solid; border-top-width: 1px; border-top-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; overflow-x: hidden; }
 #xgmntcxysw .gt_stub { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; }
 #xgmntcxysw .gt_indent_1 { text-indent: 5px; }
 #xgmntcxysw .gt_indent_2 { text-indent: calc(5px * 2); }
 #xgmntcxysw .gt_indent_3 { text-indent: calc(5px * 3); }
 #xgmntcxysw .gt_indent_4 { text-indent: calc(5px * 4); }
 #xgmntcxysw .gt_indent_5 { text-indent: calc(5px * 5); }
 #xgmntcxysw .gt_stub_row_group { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; vertical-align: top; }
 #xgmntcxysw .gt_row_group_first td { border-top-width: 2px; }
 #xgmntcxysw .gt_row_group_first th { border-top-width: 2px; }
 #xgmntcxysw .gt_striped { color: #333333; background-color: #F4F4F4; }
 #xgmntcxysw .gt_table_body { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #xgmntcxysw .gt_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #xgmntcxysw .gt_first_summary_row { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; }
 #xgmntcxysw .gt_last_summary_row_top { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #xgmntcxysw .gt_grand_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #xgmntcxysw .gt_first_grand_summary_row_bottom { border-top-style: double; border-top-width: 6px; border-top-color: #D3D3D3; }
 #xgmntcxysw .gt_last_grand_summary_row_top { border-bottom-style: double; border-bottom-width: 6px; border-bottom-color: #D3D3D3; }
 #xgmntcxysw .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #xgmntcxysw .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #xgmntcxysw .gt_left { text-align: left; }
 #xgmntcxysw .gt_center { text-align: center; }
 #xgmntcxysw .gt_right { text-align: right; font-variant-numeric: tabular-nums; }
 #xgmntcxysw .gt_font_normal { font-weight: normal; }
 #xgmntcxysw .gt_font_bold { font-weight: bold; }
 #xgmntcxysw .gt_font_italic { font-style: italic; }
 #xgmntcxysw .gt_super { font-size: 65%; }
 #xgmntcxysw .gt_footnotes { color: font-color(#FFFFFF); background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #xgmntcxysw .gt_footnote { margin: 0px; font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; }
 #xgmntcxysw .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #xgmntcxysw .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #xgmntcxysw .gt_footnote_marks { font-size: 75%; vertical-align: 0.4em; position: initial; }
 #xgmntcxysw .gt_asterisk { font-size: 100%; vertical-align: 0; }
 &#10;</style>

| DARKO forward validation — projection (t) vs realized RAPM (t+1) |  |  |  |
|----|----|----|----|
| out-of-sample by construction; weighted mean r = 0.362 over 28 season pairs |  |  |  |
| season | pearson | MAE | n |
| 2014 | 0.375 | 1.901 | 395 |
| 2015 | 0.440 | 1.550 | 396 |
| 2016 | 0.406 | 1.583 | 386 |
| 2017 | 0.322 | 1.930 | 392 |
| 2018 | 0.423 | 1.456 | 412 |
| 2019 | 0.352 | 1.061 | 400 |
| 2020 | 0.242 | 1.069 | 435 |
| 2021 | 0.380 | 1.019 | 450 |
| 2022 | 0.376 | 1.035 | 433 |
| 2023 | 0.394 | 1.058 | 450 |
| 2024 | 0.395 | 1.041 | 447 |
| 2025 | 0.330 | 1.707 | 464 |

&#10;</div>

<img src="player_impact_files/figure-commonmark/cell-8-output-1.png"
width="420" height="300"
alt="DARKO forward correlation by projection season — modest and stable, capped by RAPM noise in the target." />

<div id="pmxmejxqun" style="padding-left:0px;padding-right:0px;padding-top:10px;padding-bottom:10px;overflow-x:auto;overflow-y:auto;width:auto;height:auto;">
<style>
#pmxmejxqun table {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', 'Fira Sans', 'Droid Sans', Arial, sans-serif;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }
&#10;#pmxmejxqun thead, tbody, tfoot, tr, td, th { border-style: none; }
 tr { background-color: transparent; }
#pmxmejxqun p { margin: 0; padding: 0; }
 #pmxmejxqun .gt_table { display: table; border-collapse: collapse; line-height: normal; margin-left: auto; margin-right: auto; color: #333333; font-size: 16px; font-weight: normal; font-style: normal; background-color: #FFFFFF; width: auto; border-top-style: solid; border-top-width: 2px; border-top-color: #A8A8A8; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #A8A8A8; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; }
 #pmxmejxqun .gt_caption { padding-top: 4px; padding-bottom: 4px; }
 #pmxmejxqun .gt_title { color: #333333; font-size: 125%; font-weight: initial; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; border-bottom-color: #FFFFFF; border-bottom-width: 0; }
 #pmxmejxqun .gt_subtitle { color: #333333; font-size: 85%; font-weight: initial; padding-top: 3px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; border-top-color: #FFFFFF; border-top-width: 0; }
 #pmxmejxqun .gt_heading { background-color: #FFFFFF; text-align: center; border-bottom-color: #FFFFFF; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #pmxmejxqun .gt_bottom_border { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #pmxmejxqun .gt_col_headings { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #pmxmejxqun .gt_col_heading { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; overflow-x: hidden; }
 #pmxmejxqun .gt_column_spanner_outer { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; padding-top: 0; padding-bottom: 0; padding-left: 4px; padding-right: 4px; }
 #pmxmejxqun .gt_column_spanner_outer:first-child { padding-left: 0; }
 #pmxmejxqun .gt_column_spanner_outer:last-child { padding-right: 0; }
 #pmxmejxqun .gt_column_spanner { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; overflow-x: hidden; display: inline-block; width: 100%; }
 #pmxmejxqun .gt_spanner_row { border-bottom-style: hidden; }
 #pmxmejxqun .gt_group_heading { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; text-align: left; }
 #pmxmejxqun .gt_empty_group_heading { padding: 0.5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: middle; }
 #pmxmejxqun .gt_from_md> :first-child { margin-top: 0; }
 #pmxmejxqun .gt_from_md> :last-child { margin-bottom: 0; }
 #pmxmejxqun .gt_row { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; margin: 10px; border-top-style: solid; border-top-width: 1px; border-top-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; overflow-x: hidden; }
 #pmxmejxqun .gt_stub { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; }
 #pmxmejxqun .gt_indent_1 { text-indent: 5px; }
 #pmxmejxqun .gt_indent_2 { text-indent: calc(5px * 2); }
 #pmxmejxqun .gt_indent_3 { text-indent: calc(5px * 3); }
 #pmxmejxqun .gt_indent_4 { text-indent: calc(5px * 4); }
 #pmxmejxqun .gt_indent_5 { text-indent: calc(5px * 5); }
 #pmxmejxqun .gt_stub_row_group { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; vertical-align: top; }
 #pmxmejxqun .gt_row_group_first td { border-top-width: 2px; }
 #pmxmejxqun .gt_row_group_first th { border-top-width: 2px; }
 #pmxmejxqun .gt_striped { color: #333333; background-color: #F4F4F4; }
 #pmxmejxqun .gt_table_body { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #pmxmejxqun .gt_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #pmxmejxqun .gt_first_summary_row { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; }
 #pmxmejxqun .gt_last_summary_row_top { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #pmxmejxqun .gt_grand_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #pmxmejxqun .gt_first_grand_summary_row_bottom { border-top-style: double; border-top-width: 6px; border-top-color: #D3D3D3; }
 #pmxmejxqun .gt_last_grand_summary_row_top { border-bottom-style: double; border-bottom-width: 6px; border-bottom-color: #D3D3D3; }
 #pmxmejxqun .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #pmxmejxqun .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #pmxmejxqun .gt_left { text-align: left; }
 #pmxmejxqun .gt_center { text-align: center; }
 #pmxmejxqun .gt_right { text-align: right; font-variant-numeric: tabular-nums; }
 #pmxmejxqun .gt_font_normal { font-weight: normal; }
 #pmxmejxqun .gt_font_bold { font-weight: bold; }
 #pmxmejxqun .gt_font_italic { font-style: italic; }
 #pmxmejxqun .gt_super { font-size: 65%; }
 #pmxmejxqun .gt_footnotes { color: font-color(#FFFFFF); background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #pmxmejxqun .gt_footnote { margin: 0px; font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; }
 #pmxmejxqun .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #pmxmejxqun .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #pmxmejxqun .gt_footnote_marks { font-size: 75%; vertical-align: 0.4em; position: initial; }
 #pmxmejxqun .gt_asterisk { font-size: 100%; vertical-align: 0; }
 &#10;</style>

| Reliability context for the forward validation |  |  |
|----|----|----|
| the projection's ceiling is bounded by how noisy the RAPM target itself is |  |  |
| check | pearson | pairs |
| RAPM year-over-year reliability (same player, adjacent seasons) | 0.357 | 11272 |
| adj-RAPM vs RAPM agreement (2026 RS) | 0.913 | 582 |

&#10;</div>

The forward-r is honest but modest, and the reliability row is why:
DARKO cannot correlate with next-season RAPM more than next-season RAPM
correlates with anything stable. The engines were additionally
proxy-validated against the published RAPM/EPM oracle CSVs at build time
(beating the minutes-played baseline by ~10%); numeric publish-blocking
floors remain a recorded TODO in `models/REGISTRY.md`.

## Results

<div id="esppijhdxr" style="padding-left:0px;padding-right:0px;padding-top:10px;padding-bottom:10px;overflow-x:auto;overflow-y:auto;width:auto;height:auto;">
<style>
#esppijhdxr table {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', 'Fira Sans', 'Droid Sans', Arial, sans-serif;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }
&#10;#esppijhdxr thead, tbody, tfoot, tr, td, th { border-style: none; }
 tr { background-color: transparent; }
#esppijhdxr p { margin: 0; padding: 0; }
 #esppijhdxr .gt_table { display: table; border-collapse: collapse; line-height: normal; margin-left: auto; margin-right: auto; color: #333333; font-size: 16px; font-weight: normal; font-style: normal; background-color: #FFFFFF; width: auto; border-top-style: solid; border-top-width: 2px; border-top-color: #A8A8A8; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #A8A8A8; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; }
 #esppijhdxr .gt_caption { padding-top: 4px; padding-bottom: 4px; }
 #esppijhdxr .gt_title { color: #333333; font-size: 125%; font-weight: initial; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; border-bottom-color: #FFFFFF; border-bottom-width: 0; }
 #esppijhdxr .gt_subtitle { color: #333333; font-size: 85%; font-weight: initial; padding-top: 3px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; border-top-color: #FFFFFF; border-top-width: 0; }
 #esppijhdxr .gt_heading { background-color: #FFFFFF; text-align: center; border-bottom-color: #FFFFFF; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #esppijhdxr .gt_bottom_border { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #esppijhdxr .gt_col_headings { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #esppijhdxr .gt_col_heading { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; overflow-x: hidden; }
 #esppijhdxr .gt_column_spanner_outer { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; padding-top: 0; padding-bottom: 0; padding-left: 4px; padding-right: 4px; }
 #esppijhdxr .gt_column_spanner_outer:first-child { padding-left: 0; }
 #esppijhdxr .gt_column_spanner_outer:last-child { padding-right: 0; }
 #esppijhdxr .gt_column_spanner { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; overflow-x: hidden; display: inline-block; width: 100%; }
 #esppijhdxr .gt_spanner_row { border-bottom-style: hidden; }
 #esppijhdxr .gt_group_heading { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; text-align: left; }
 #esppijhdxr .gt_empty_group_heading { padding: 0.5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: middle; }
 #esppijhdxr .gt_from_md> :first-child { margin-top: 0; }
 #esppijhdxr .gt_from_md> :last-child { margin-bottom: 0; }
 #esppijhdxr .gt_row { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; margin: 10px; border-top-style: solid; border-top-width: 1px; border-top-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; overflow-x: hidden; }
 #esppijhdxr .gt_stub { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; }
 #esppijhdxr .gt_indent_1 { text-indent: 5px; }
 #esppijhdxr .gt_indent_2 { text-indent: calc(5px * 2); }
 #esppijhdxr .gt_indent_3 { text-indent: calc(5px * 3); }
 #esppijhdxr .gt_indent_4 { text-indent: calc(5px * 4); }
 #esppijhdxr .gt_indent_5 { text-indent: calc(5px * 5); }
 #esppijhdxr .gt_stub_row_group { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; vertical-align: top; }
 #esppijhdxr .gt_row_group_first td { border-top-width: 2px; }
 #esppijhdxr .gt_row_group_first th { border-top-width: 2px; }
 #esppijhdxr .gt_striped { color: #333333; background-color: #F4F4F4; }
 #esppijhdxr .gt_table_body { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #esppijhdxr .gt_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #esppijhdxr .gt_first_summary_row { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; }
 #esppijhdxr .gt_last_summary_row_top { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #esppijhdxr .gt_grand_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #esppijhdxr .gt_first_grand_summary_row_bottom { border-top-style: double; border-top-width: 6px; border-top-color: #D3D3D3; }
 #esppijhdxr .gt_last_grand_summary_row_top { border-bottom-style: double; border-bottom-width: 6px; border-bottom-color: #D3D3D3; }
 #esppijhdxr .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #esppijhdxr .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #esppijhdxr .gt_left { text-align: left; }
 #esppijhdxr .gt_center { text-align: center; }
 #esppijhdxr .gt_right { text-align: right; font-variant-numeric: tabular-nums; }
 #esppijhdxr .gt_font_normal { font-weight: normal; }
 #esppijhdxr .gt_font_bold { font-weight: bold; }
 #esppijhdxr .gt_font_italic { font-style: italic; }
 #esppijhdxr .gt_super { font-size: 65%; }
 #esppijhdxr .gt_footnotes { color: font-color(#FFFFFF); background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #esppijhdxr .gt_footnote { margin: 0px; font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; }
 #esppijhdxr .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #esppijhdxr .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #esppijhdxr .gt_footnote_marks { font-size: 75%; vertical-align: 0.4em; position: initial; }
 #esppijhdxr .gt_asterisk { font-size: 100%; vertical-align: 0; }
 &#10;</style>

| Top 15 by WAR — 2026 regular season (min 500 minutes) |  |  |  |  |  |  |  |  |
|----|----|----|----|----|----|----|----|----|
|  | Player | Team | GP | Min | RAPM | adj-RAPM | BPM | WAR |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1628983.png"
height="40" /> | Shai Gilgeous-Alexander | OKC | 68 | 2,261 | 8.00 | 13.64 | 19.79 | 24.89 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1630700.png"
height="40" /> | Dyson Daniels | ATL | 76 | 2,523 | 6.73 | 13.63 | 3.34 | 24.82 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1631096.png"
height="40" /> | Chet Holmgren | OKC | 69 | 1,997 | 7.38 | 12.21 | 12.41 | 20.90 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/202695.png"
height="40" /> | Kawhi Leonard | LAC | 65 | 2,087 | 7.32 | 12.93 | 6.75 | 20.82 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1628401.png"
height="40" /> | Derrick White | BOS | 77 | 2,623 | 5.49 | 8.16 | 9.65 | 20.82 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1641705.png"
height="40" /> | Victor Wembanyama | SAS | 64 | 1,867 | 7.87 | 12.19 | 14.34 | 20.43 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1641708.png"
height="40" /> | Amen Thompson | HOU | 79 | 2,954 | 4.35 | 8.07 | 7.21 | 19.94 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1628389.png"
height="40" /> | Bam Adebayo | MIA | 73 | 2,363 | 5.37 | 10.15 | 2.55 | 19.79 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/203999.png"
height="40" /> | Nikola Jokić | DEN | 65 | 2,265 | 5.74 | 9.90 | 18.00 | 18.85 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1628378.png"
height="40" /> | Donovan Mitchell | CLE | 70 | 2,341 | 4.81 | 7.38 | 7.75 | 17.99 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1629638.png"
height="40" /> | Nickeil Alexander-Walker | ATL | 78 | 2,603 | 3.98 | 8.45 | 2.51 | 17.77 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1630577.png"
height="40" /> | Julian Champagnie | SAS | 82 | 2,267 | 4.88 | 7.52 | 7.19 | 17.33 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1628978.png"
height="40" /> | Donte DiVincenzo | MIN | 82 | 2,497 | 4.07 | 6.38 | 3.90 | 16.87 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1630595.png"
height="40" /> | Cade Cunningham | DET | 64 | 2,172 | 5.02 | 8.58 | 12.94 | 16.71 |
| <img src="https://cdn.nba.com/headshots/nba/latest/260x190/1626164.png"
height="40" /> | Devin Booker | PHX | 64 | 2,148 | 4.96 | 10.32 | 3.38 | 16.26 |

&#10;</div>

## Provenance & reproducibility

- **Trained on:** the committed `hoopR-nba-stats-raw` store (possession
  compile from per-game playbyplay/rotation/boxscore + season-level
  leaguegamelog / playerindex / leaguedashplayerbiostats captures),
  seasons 1997–2026 (the corpus table above lists what the release
  carries), read offline through the raw-store backend.
- **Pipeline:** per-engine numbered stages `nba_model_01_possessions` …
  `nba_model_07_darko` (parquet handoffs under
  `build_out/impact_engines/`; hermetic stub tests cover the chain
  including cross-season prior threading), consolidated build+publish as
  `nba_model_08_impact`. Retrain is dispatch-only BY DESIGN
  (rate-budgeted; `dry_run` defaults true); full-history backfills run
  from the droplet. Single home: `models/manifest.yaml`.
- **This document** evaluates the published `nba_player_impact` release
  assets downloaded at render time — the exact frames consumers read.
- **Rebuild:** `scripts/render_model_docs.sh` (Quarto → GFM;
  `uv sync --group docs`). Requires network for the release download and
  the headshot CDN.

## Avenues for improvement & open issues

- **Encode the numeric publish floors** — the registry states them as
  TODO; the proxy-validation deltas are exactly the values to freeze.
- **Publish the SPM coefficient vector** — the release carries the
  engine outputs but not the fitted coefficients; shipping them (or a
  per-retrain meta sidecar) would let this document show real
  coefficient importance instead of describing where it lives.
- **Uncertainty** — none of the engines ships an interval; a
  cluster-respecting resample (games, not rows) is the recorded
  standard.
- **DARKO ceiling** — the forward-r is capped by RAPM noise in the
  target; validating against a multi-season blended target would
  separate projection error from target noise.
- **PlayIn season type is unsupported** by design; revisit if the sample
  ever justifies it.
