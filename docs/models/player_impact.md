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

<div id="fusblihmjw" style="padding-left:0px;padding-right:0px;padding-top:10px;padding-bottom:10px;overflow-x:auto;overflow-y:auto;width:auto;height:auto;">
<style>
#fusblihmjw table {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', 'Fira Sans', 'Droid Sans', Arial, sans-serif;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }
&#10;#fusblihmjw thead, tbody, tfoot, tr, td, th { border-style: none; }
 tr { background-color: transparent; }
#fusblihmjw p { margin: 0; padding: 0; }
 #fusblihmjw .gt_table { display: table; border-collapse: collapse; line-height: normal; margin-left: auto; margin-right: auto; color: #333333; font-size: 16px; font-weight: normal; font-style: normal; background-color: #FFFFFF; width: auto; border-top-style: solid; border-top-width: 2px; border-top-color: #A8A8A8; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #A8A8A8; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; }
 #fusblihmjw .gt_caption { padding-top: 4px; padding-bottom: 4px; }
 #fusblihmjw .gt_title { color: #333333; font-size: 125%; font-weight: initial; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; border-bottom-color: #FFFFFF; border-bottom-width: 0; }
 #fusblihmjw .gt_subtitle { color: #333333; font-size: 85%; font-weight: initial; padding-top: 3px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; border-top-color: #FFFFFF; border-top-width: 0; }
 #fusblihmjw .gt_heading { background-color: #FFFFFF; text-align: center; border-bottom-color: #FFFFFF; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #fusblihmjw .gt_bottom_border { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #fusblihmjw .gt_col_headings { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #fusblihmjw .gt_col_heading { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; overflow-x: hidden; }
 #fusblihmjw .gt_column_spanner_outer { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; padding-top: 0; padding-bottom: 0; padding-left: 4px; padding-right: 4px; }
 #fusblihmjw .gt_column_spanner_outer:first-child { padding-left: 0; }
 #fusblihmjw .gt_column_spanner_outer:last-child { padding-right: 0; }
 #fusblihmjw .gt_column_spanner { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; overflow-x: hidden; display: inline-block; width: 100%; }
 #fusblihmjw .gt_spanner_row { border-bottom-style: hidden; }
 #fusblihmjw .gt_group_heading { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; text-align: left; }
 #fusblihmjw .gt_empty_group_heading { padding: 0.5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: middle; }
 #fusblihmjw .gt_from_md> :first-child { margin-top: 0; }
 #fusblihmjw .gt_from_md> :last-child { margin-bottom: 0; }
 #fusblihmjw .gt_row { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; margin: 10px; border-top-style: solid; border-top-width: 1px; border-top-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; overflow-x: hidden; }
 #fusblihmjw .gt_stub { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; }
 #fusblihmjw .gt_indent_1 { text-indent: 5px; }
 #fusblihmjw .gt_indent_2 { text-indent: calc(5px * 2); }
 #fusblihmjw .gt_indent_3 { text-indent: calc(5px * 3); }
 #fusblihmjw .gt_indent_4 { text-indent: calc(5px * 4); }
 #fusblihmjw .gt_indent_5 { text-indent: calc(5px * 5); }
 #fusblihmjw .gt_stub_row_group { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; vertical-align: top; }
 #fusblihmjw .gt_row_group_first td { border-top-width: 2px; }
 #fusblihmjw .gt_row_group_first th { border-top-width: 2px; }
 #fusblihmjw .gt_striped { color: #333333; background-color: #F4F4F4; }
 #fusblihmjw .gt_table_body { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #fusblihmjw .gt_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #fusblihmjw .gt_first_summary_row { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; }
 #fusblihmjw .gt_last_summary_row_top { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #fusblihmjw .gt_grand_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #fusblihmjw .gt_first_grand_summary_row_bottom { border-top-style: double; border-top-width: 6px; border-top-color: #D3D3D3; }
 #fusblihmjw .gt_last_grand_summary_row_top { border-bottom-style: double; border-bottom-width: 6px; border-bottom-color: #D3D3D3; }
 #fusblihmjw .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #fusblihmjw .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #fusblihmjw .gt_left { text-align: left; }
 #fusblihmjw .gt_center { text-align: center; }
 #fusblihmjw .gt_right { text-align: right; font-variant-numeric: tabular-nums; }
 #fusblihmjw .gt_font_normal { font-weight: normal; }
 #fusblihmjw .gt_font_bold { font-weight: bold; }
 #fusblihmjw .gt_font_italic { font-style: italic; }
 #fusblihmjw .gt_super { font-size: 65%; }
 #fusblihmjw .gt_footnotes { color: font-color(#FFFFFF); background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #fusblihmjw .gt_footnote { margin: 0px; font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; }
 #fusblihmjw .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #fusblihmjw .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #fusblihmjw .gt_footnote_marks { font-size: 75%; vertical-align: 0.4em; position: initial; }
 #fusblihmjw .gt_asterisk { font-size: 100%; vertical-align: 0; }
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
needed — the columns are the exact attributions.

The SPM coefficient vector itself now ships as an additive sidecar,
`nba_player_impact_spm_coefficients.json`: one record per season with
the offense and defense ridge coefficients, the feature names, the fit
population’s per-100 feature standard deviations, and the train-time fit
metrics. So this section shows the fitted model rather than describing
where it lives.

<div id="ztxosrfpft" style="padding-left:0px;padding-right:0px;padding-top:10px;padding-bottom:10px;overflow-x:auto;overflow-y:auto;width:auto;height:auto;">
<style>
#ztxosrfpft table {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', 'Fira Sans', 'Droid Sans', Arial, sans-serif;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }
&#10;#ztxosrfpft thead, tbody, tfoot, tr, td, th { border-style: none; }
 tr { background-color: transparent; }
#ztxosrfpft p { margin: 0; padding: 0; }
 #ztxosrfpft .gt_table { display: table; border-collapse: collapse; line-height: normal; margin-left: auto; margin-right: auto; color: #333333; font-size: 16px; font-weight: normal; font-style: normal; background-color: #FFFFFF; width: auto; border-top-style: solid; border-top-width: 2px; border-top-color: #A8A8A8; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #A8A8A8; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; }
 #ztxosrfpft .gt_caption { padding-top: 4px; padding-bottom: 4px; }
 #ztxosrfpft .gt_title { color: #333333; font-size: 125%; font-weight: initial; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; border-bottom-color: #FFFFFF; border-bottom-width: 0; }
 #ztxosrfpft .gt_subtitle { color: #333333; font-size: 85%; font-weight: initial; padding-top: 3px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; border-top-color: #FFFFFF; border-top-width: 0; }
 #ztxosrfpft .gt_heading { background-color: #FFFFFF; text-align: center; border-bottom-color: #FFFFFF; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #ztxosrfpft .gt_bottom_border { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #ztxosrfpft .gt_col_headings { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #ztxosrfpft .gt_col_heading { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; overflow-x: hidden; }
 #ztxosrfpft .gt_column_spanner_outer { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; padding-top: 0; padding-bottom: 0; padding-left: 4px; padding-right: 4px; }
 #ztxosrfpft .gt_column_spanner_outer:first-child { padding-left: 0; }
 #ztxosrfpft .gt_column_spanner_outer:last-child { padding-right: 0; }
 #ztxosrfpft .gt_column_spanner { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; overflow-x: hidden; display: inline-block; width: 100%; }
 #ztxosrfpft .gt_spanner_row { border-bottom-style: hidden; }
 #ztxosrfpft .gt_group_heading { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; text-align: left; }
 #ztxosrfpft .gt_empty_group_heading { padding: 0.5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: middle; }
 #ztxosrfpft .gt_from_md> :first-child { margin-top: 0; }
 #ztxosrfpft .gt_from_md> :last-child { margin-bottom: 0; }
 #ztxosrfpft .gt_row { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; margin: 10px; border-top-style: solid; border-top-width: 1px; border-top-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; overflow-x: hidden; }
 #ztxosrfpft .gt_stub { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; }
 #ztxosrfpft .gt_indent_1 { text-indent: 5px; }
 #ztxosrfpft .gt_indent_2 { text-indent: calc(5px * 2); }
 #ztxosrfpft .gt_indent_3 { text-indent: calc(5px * 3); }
 #ztxosrfpft .gt_indent_4 { text-indent: calc(5px * 4); }
 #ztxosrfpft .gt_indent_5 { text-indent: calc(5px * 5); }
 #ztxosrfpft .gt_stub_row_group { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; vertical-align: top; }
 #ztxosrfpft .gt_row_group_first td { border-top-width: 2px; }
 #ztxosrfpft .gt_row_group_first th { border-top-width: 2px; }
 #ztxosrfpft .gt_striped { color: #333333; background-color: #F4F4F4; }
 #ztxosrfpft .gt_table_body { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #ztxosrfpft .gt_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #ztxosrfpft .gt_first_summary_row { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; }
 #ztxosrfpft .gt_last_summary_row_top { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #ztxosrfpft .gt_grand_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #ztxosrfpft .gt_first_grand_summary_row_bottom { border-top-style: double; border-top-width: 6px; border-top-color: #D3D3D3; }
 #ztxosrfpft .gt_last_grand_summary_row_top { border-bottom-style: double; border-bottom-width: 6px; border-bottom-color: #D3D3D3; }
 #ztxosrfpft .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #ztxosrfpft .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #ztxosrfpft .gt_left { text-align: left; }
 #ztxosrfpft .gt_center { text-align: center; }
 #ztxosrfpft .gt_right { text-align: right; font-variant-numeric: tabular-nums; }
 #ztxosrfpft .gt_font_normal { font-weight: normal; }
 #ztxosrfpft .gt_font_bold { font-weight: bold; }
 #ztxosrfpft .gt_font_italic { font-style: italic; }
 #ztxosrfpft .gt_super { font-size: 65%; }
 #ztxosrfpft .gt_footnotes { color: font-color(#FFFFFF); background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #ztxosrfpft .gt_footnote { margin: 0px; font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; }
 #ztxosrfpft .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #ztxosrfpft .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #ztxosrfpft .gt_footnote_marks { font-size: 75%; vertical-align: 0.4em; position: initial; }
 #ztxosrfpft .gt_asterisk { font-size: 100%; vertical-align: 0; }
 &#10;</style>

| Fitted SPM coefficients — 2026 (ridge, alpha = 100) |  |  |  |  |  |
|----|----|----|----|----|----|
| source: repo copy (nba_player_impact_spm_coefficients.json); fit on 582 regular-season players, train r(spm, rapm) = 0.437 |  |  |  |  |  |
| feature | o_coef | d_coef | feature SD | \|o_coef\|×SD | \|d_coef\|×SD |
| pts | 0.136 | 0.008 | 7.298 | 0.996 | 0.057 |
| fga | −0.060 | −0.024 | 4.968 | 0.298 | 0.121 |
| ast | 0.094 | 0.025 | 2.710 | 0.254 | 0.067 |
| tov | −0.177 | −0.063 | 1.287 | 0.228 | 0.081 |
| oreb | 0.056 | 0.050 | 1.897 | 0.106 | 0.096 |
| dreb | 0.036 | 0.082 | 2.746 | 0.098 | 0.225 |
| blk | −0.083 | 0.228 | 0.951 | 0.079 | 0.217 |
| pf | −0.019 | −0.055 | 1.643 | 0.031 | 0.090 |
| stl | 0.024 | 0.245 | 0.878 | 0.021 | 0.215 |
| fg3m | 0.009 | 0.082 | 1.568 | 0.013 | 0.129 |
| fta | −0.004 | −0.017 | 2.889 | 0.013 | 0.048 |

&#10;</div>

<img src="player_impact_files/figure-commonmark/cell-8-output-1.png"
width="420" height="300"
alt="Offensive SPM importance — points per 100 attributable to a 1-SD move in each per-100 box feature." />

The sidecar is reproducible from the published data itself: refitting
each season on its released `o_rapm`/`d_rapm` target plus the same
committed box logs recovers the published `spm` column exactly in 29 of
30 seasons (max absolute difference 0.0; 2005 differs by 0.158 at the
extreme, r = 0.999962 — a box-log difference in that one season,
recorded rather than smoothed over). That check is stored per record as
`reproduces_published_spm_r`, so a refit that did *not* reproduce the
release would show up in the artifact instead of passing silently.

<img src="player_impact_files/figure-commonmark/cell-9-output-1.png"
width="420" height="300"
alt="adj-RAPM vs RAPM, latest regular season — the SPM prior shrinks, it does not overwrite." />

## Evaluation

**DARKO forward validation** is the suite’s headline out-of-sample test:
the projection made in season t (`darko_projected_rating`, which sees
nothing after t) against the realized RAPM in season t+1. Recomputed at
render time over every adjacent published season pair:

<div id="zyslvjgiyk" style="padding-left:0px;padding-right:0px;padding-top:10px;padding-bottom:10px;overflow-x:auto;overflow-y:auto;width:auto;height:auto;">
<style>
#zyslvjgiyk table {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', 'Fira Sans', 'Droid Sans', Arial, sans-serif;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }
&#10;#zyslvjgiyk thead, tbody, tfoot, tr, td, th { border-style: none; }
 tr { background-color: transparent; }
#zyslvjgiyk p { margin: 0; padding: 0; }
 #zyslvjgiyk .gt_table { display: table; border-collapse: collapse; line-height: normal; margin-left: auto; margin-right: auto; color: #333333; font-size: 16px; font-weight: normal; font-style: normal; background-color: #FFFFFF; width: auto; border-top-style: solid; border-top-width: 2px; border-top-color: #A8A8A8; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #A8A8A8; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; }
 #zyslvjgiyk .gt_caption { padding-top: 4px; padding-bottom: 4px; }
 #zyslvjgiyk .gt_title { color: #333333; font-size: 125%; font-weight: initial; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; border-bottom-color: #FFFFFF; border-bottom-width: 0; }
 #zyslvjgiyk .gt_subtitle { color: #333333; font-size: 85%; font-weight: initial; padding-top: 3px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; border-top-color: #FFFFFF; border-top-width: 0; }
 #zyslvjgiyk .gt_heading { background-color: #FFFFFF; text-align: center; border-bottom-color: #FFFFFF; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #zyslvjgiyk .gt_bottom_border { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #zyslvjgiyk .gt_col_headings { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #zyslvjgiyk .gt_col_heading { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; overflow-x: hidden; }
 #zyslvjgiyk .gt_column_spanner_outer { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; padding-top: 0; padding-bottom: 0; padding-left: 4px; padding-right: 4px; }
 #zyslvjgiyk .gt_column_spanner_outer:first-child { padding-left: 0; }
 #zyslvjgiyk .gt_column_spanner_outer:last-child { padding-right: 0; }
 #zyslvjgiyk .gt_column_spanner { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; overflow-x: hidden; display: inline-block; width: 100%; }
 #zyslvjgiyk .gt_spanner_row { border-bottom-style: hidden; }
 #zyslvjgiyk .gt_group_heading { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; text-align: left; }
 #zyslvjgiyk .gt_empty_group_heading { padding: 0.5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: middle; }
 #zyslvjgiyk .gt_from_md> :first-child { margin-top: 0; }
 #zyslvjgiyk .gt_from_md> :last-child { margin-bottom: 0; }
 #zyslvjgiyk .gt_row { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; margin: 10px; border-top-style: solid; border-top-width: 1px; border-top-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; overflow-x: hidden; }
 #zyslvjgiyk .gt_stub { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; }
 #zyslvjgiyk .gt_indent_1 { text-indent: 5px; }
 #zyslvjgiyk .gt_indent_2 { text-indent: calc(5px * 2); }
 #zyslvjgiyk .gt_indent_3 { text-indent: calc(5px * 3); }
 #zyslvjgiyk .gt_indent_4 { text-indent: calc(5px * 4); }
 #zyslvjgiyk .gt_indent_5 { text-indent: calc(5px * 5); }
 #zyslvjgiyk .gt_stub_row_group { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; vertical-align: top; }
 #zyslvjgiyk .gt_row_group_first td { border-top-width: 2px; }
 #zyslvjgiyk .gt_row_group_first th { border-top-width: 2px; }
 #zyslvjgiyk .gt_striped { color: #333333; background-color: #F4F4F4; }
 #zyslvjgiyk .gt_table_body { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #zyslvjgiyk .gt_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #zyslvjgiyk .gt_first_summary_row { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; }
 #zyslvjgiyk .gt_last_summary_row_top { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #zyslvjgiyk .gt_grand_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #zyslvjgiyk .gt_first_grand_summary_row_bottom { border-top-style: double; border-top-width: 6px; border-top-color: #D3D3D3; }
 #zyslvjgiyk .gt_last_grand_summary_row_top { border-bottom-style: double; border-bottom-width: 6px; border-bottom-color: #D3D3D3; }
 #zyslvjgiyk .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #zyslvjgiyk .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #zyslvjgiyk .gt_left { text-align: left; }
 #zyslvjgiyk .gt_center { text-align: center; }
 #zyslvjgiyk .gt_right { text-align: right; font-variant-numeric: tabular-nums; }
 #zyslvjgiyk .gt_font_normal { font-weight: normal; }
 #zyslvjgiyk .gt_font_bold { font-weight: bold; }
 #zyslvjgiyk .gt_font_italic { font-style: italic; }
 #zyslvjgiyk .gt_super { font-size: 65%; }
 #zyslvjgiyk .gt_footnotes { color: font-color(#FFFFFF); background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #zyslvjgiyk .gt_footnote { margin: 0px; font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; }
 #zyslvjgiyk .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #zyslvjgiyk .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #zyslvjgiyk .gt_footnote_marks { font-size: 75%; vertical-align: 0.4em; position: initial; }
 #zyslvjgiyk .gt_asterisk { font-size: 100%; vertical-align: 0; }
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

<img src="player_impact_files/figure-commonmark/cell-11-output-1.png"
width="420" height="300"
alt="DARKO forward correlation by projection season — modest and stable, capped by RAPM noise in the target." />

<div id="bwpgmkjcop" style="padding-left:0px;padding-right:0px;padding-top:10px;padding-bottom:10px;overflow-x:auto;overflow-y:auto;width:auto;height:auto;">
<style>
#bwpgmkjcop table {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', 'Fira Sans', 'Droid Sans', Arial, sans-serif;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }
&#10;#bwpgmkjcop thead, tbody, tfoot, tr, td, th { border-style: none; }
 tr { background-color: transparent; }
#bwpgmkjcop p { margin: 0; padding: 0; }
 #bwpgmkjcop .gt_table { display: table; border-collapse: collapse; line-height: normal; margin-left: auto; margin-right: auto; color: #333333; font-size: 16px; font-weight: normal; font-style: normal; background-color: #FFFFFF; width: auto; border-top-style: solid; border-top-width: 2px; border-top-color: #A8A8A8; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #A8A8A8; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; }
 #bwpgmkjcop .gt_caption { padding-top: 4px; padding-bottom: 4px; }
 #bwpgmkjcop .gt_title { color: #333333; font-size: 125%; font-weight: initial; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; border-bottom-color: #FFFFFF; border-bottom-width: 0; }
 #bwpgmkjcop .gt_subtitle { color: #333333; font-size: 85%; font-weight: initial; padding-top: 3px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; border-top-color: #FFFFFF; border-top-width: 0; }
 #bwpgmkjcop .gt_heading { background-color: #FFFFFF; text-align: center; border-bottom-color: #FFFFFF; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #bwpgmkjcop .gt_bottom_border { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #bwpgmkjcop .gt_col_headings { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #bwpgmkjcop .gt_col_heading { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; overflow-x: hidden; }
 #bwpgmkjcop .gt_column_spanner_outer { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; padding-top: 0; padding-bottom: 0; padding-left: 4px; padding-right: 4px; }
 #bwpgmkjcop .gt_column_spanner_outer:first-child { padding-left: 0; }
 #bwpgmkjcop .gt_column_spanner_outer:last-child { padding-right: 0; }
 #bwpgmkjcop .gt_column_spanner { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; overflow-x: hidden; display: inline-block; width: 100%; }
 #bwpgmkjcop .gt_spanner_row { border-bottom-style: hidden; }
 #bwpgmkjcop .gt_group_heading { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; text-align: left; }
 #bwpgmkjcop .gt_empty_group_heading { padding: 0.5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: middle; }
 #bwpgmkjcop .gt_from_md> :first-child { margin-top: 0; }
 #bwpgmkjcop .gt_from_md> :last-child { margin-bottom: 0; }
 #bwpgmkjcop .gt_row { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; margin: 10px; border-top-style: solid; border-top-width: 1px; border-top-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; overflow-x: hidden; }
 #bwpgmkjcop .gt_stub { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; }
 #bwpgmkjcop .gt_indent_1 { text-indent: 5px; }
 #bwpgmkjcop .gt_indent_2 { text-indent: calc(5px * 2); }
 #bwpgmkjcop .gt_indent_3 { text-indent: calc(5px * 3); }
 #bwpgmkjcop .gt_indent_4 { text-indent: calc(5px * 4); }
 #bwpgmkjcop .gt_indent_5 { text-indent: calc(5px * 5); }
 #bwpgmkjcop .gt_stub_row_group { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; vertical-align: top; }
 #bwpgmkjcop .gt_row_group_first td { border-top-width: 2px; }
 #bwpgmkjcop .gt_row_group_first th { border-top-width: 2px; }
 #bwpgmkjcop .gt_striped { color: #333333; background-color: #F4F4F4; }
 #bwpgmkjcop .gt_table_body { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #bwpgmkjcop .gt_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #bwpgmkjcop .gt_first_summary_row { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; }
 #bwpgmkjcop .gt_last_summary_row_top { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #bwpgmkjcop .gt_grand_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #bwpgmkjcop .gt_first_grand_summary_row_bottom { border-top-style: double; border-top-width: 6px; border-top-color: #D3D3D3; }
 #bwpgmkjcop .gt_last_grand_summary_row_top { border-bottom-style: double; border-bottom-width: 6px; border-bottom-color: #D3D3D3; }
 #bwpgmkjcop .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #bwpgmkjcop .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #bwpgmkjcop .gt_left { text-align: left; }
 #bwpgmkjcop .gt_center { text-align: center; }
 #bwpgmkjcop .gt_right { text-align: right; font-variant-numeric: tabular-nums; }
 #bwpgmkjcop .gt_font_normal { font-weight: normal; }
 #bwpgmkjcop .gt_font_bold { font-weight: bold; }
 #bwpgmkjcop .gt_font_italic { font-style: italic; }
 #bwpgmkjcop .gt_super { font-size: 65%; }
 #bwpgmkjcop .gt_footnotes { color: font-color(#FFFFFF); background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #bwpgmkjcop .gt_footnote { margin: 0px; font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; }
 #bwpgmkjcop .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #bwpgmkjcop .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #bwpgmkjcop .gt_footnote_marks { font-size: 75%; vertical-align: 0.4em; position: initial; }
 #bwpgmkjcop .gt_asterisk { font-size: 100%; vertical-align: 0; }
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
correlates with anything stable.

### Separating projection error from target noise

A single season of RAPM is a noisy realization of a player’s true level,
so a low forward correlation confounds *the projection being wrong* with
*the target being noisy*. Averaging the target over more post-projection
seasons (possession-weighted) reduces the target’s noise without
touching the projection. Restricting all three rows to the **same**
player-seasons keeps the comparison honest — a longer target window
would otherwise also change the population:

<div id="kveclzgqsr" style="padding-left:0px;padding-right:0px;padding-top:10px;padding-bottom:10px;overflow-x:auto;overflow-y:auto;width:auto;height:auto;">
<style>
#kveclzgqsr table {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', 'Fira Sans', 'Droid Sans', Arial, sans-serif;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }
&#10;#kveclzgqsr thead, tbody, tfoot, tr, td, th { border-style: none; }
 tr { background-color: transparent; }
#kveclzgqsr p { margin: 0; padding: 0; }
 #kveclzgqsr .gt_table { display: table; border-collapse: collapse; line-height: normal; margin-left: auto; margin-right: auto; color: #333333; font-size: 16px; font-weight: normal; font-style: normal; background-color: #FFFFFF; width: auto; border-top-style: solid; border-top-width: 2px; border-top-color: #A8A8A8; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #A8A8A8; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; }
 #kveclzgqsr .gt_caption { padding-top: 4px; padding-bottom: 4px; }
 #kveclzgqsr .gt_title { color: #333333; font-size: 125%; font-weight: initial; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; border-bottom-color: #FFFFFF; border-bottom-width: 0; }
 #kveclzgqsr .gt_subtitle { color: #333333; font-size: 85%; font-weight: initial; padding-top: 3px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; border-top-color: #FFFFFF; border-top-width: 0; }
 #kveclzgqsr .gt_heading { background-color: #FFFFFF; text-align: center; border-bottom-color: #FFFFFF; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #kveclzgqsr .gt_bottom_border { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #kveclzgqsr .gt_col_headings { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #kveclzgqsr .gt_col_heading { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; overflow-x: hidden; }
 #kveclzgqsr .gt_column_spanner_outer { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; padding-top: 0; padding-bottom: 0; padding-left: 4px; padding-right: 4px; }
 #kveclzgqsr .gt_column_spanner_outer:first-child { padding-left: 0; }
 #kveclzgqsr .gt_column_spanner_outer:last-child { padding-right: 0; }
 #kveclzgqsr .gt_column_spanner { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; overflow-x: hidden; display: inline-block; width: 100%; }
 #kveclzgqsr .gt_spanner_row { border-bottom-style: hidden; }
 #kveclzgqsr .gt_group_heading { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; text-align: left; }
 #kveclzgqsr .gt_empty_group_heading { padding: 0.5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: middle; }
 #kveclzgqsr .gt_from_md> :first-child { margin-top: 0; }
 #kveclzgqsr .gt_from_md> :last-child { margin-bottom: 0; }
 #kveclzgqsr .gt_row { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; margin: 10px; border-top-style: solid; border-top-width: 1px; border-top-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; overflow-x: hidden; }
 #kveclzgqsr .gt_stub { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; }
 #kveclzgqsr .gt_indent_1 { text-indent: 5px; }
 #kveclzgqsr .gt_indent_2 { text-indent: calc(5px * 2); }
 #kveclzgqsr .gt_indent_3 { text-indent: calc(5px * 3); }
 #kveclzgqsr .gt_indent_4 { text-indent: calc(5px * 4); }
 #kveclzgqsr .gt_indent_5 { text-indent: calc(5px * 5); }
 #kveclzgqsr .gt_stub_row_group { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; vertical-align: top; }
 #kveclzgqsr .gt_row_group_first td { border-top-width: 2px; }
 #kveclzgqsr .gt_row_group_first th { border-top-width: 2px; }
 #kveclzgqsr .gt_striped { color: #333333; background-color: #F4F4F4; }
 #kveclzgqsr .gt_table_body { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #kveclzgqsr .gt_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #kveclzgqsr .gt_first_summary_row { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; }
 #kveclzgqsr .gt_last_summary_row_top { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #kveclzgqsr .gt_grand_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #kveclzgqsr .gt_first_grand_summary_row_bottom { border-top-style: double; border-top-width: 6px; border-top-color: #D3D3D3; }
 #kveclzgqsr .gt_last_grand_summary_row_top { border-bottom-style: double; border-bottom-width: 6px; border-bottom-color: #D3D3D3; }
 #kveclzgqsr .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #kveclzgqsr .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #kveclzgqsr .gt_left { text-align: left; }
 #kveclzgqsr .gt_center { text-align: center; }
 #kveclzgqsr .gt_right { text-align: right; font-variant-numeric: tabular-nums; }
 #kveclzgqsr .gt_font_normal { font-weight: normal; }
 #kveclzgqsr .gt_font_bold { font-weight: bold; }
 #kveclzgqsr .gt_font_italic { font-style: italic; }
 #kveclzgqsr .gt_super { font-size: 65%; }
 #kveclzgqsr .gt_footnotes { color: font-color(#FFFFFF); background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #kveclzgqsr .gt_footnote { margin: 0px; font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; }
 #kveclzgqsr .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #kveclzgqsr .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #kveclzgqsr .gt_footnote_marks { font-size: 75%; vertical-align: 0.4em; position: initial; }
 #kveclzgqsr .gt_asterisk { font-size: 100%; vertical-align: 0; }
 &#10;</style>

| DARKO against a multi-season blended target |  |  |  |  |  |  |
|----|----|----|----|----|----|----|
| same player-seasons in every row; only the target's noise changes |  |  |  |  |  |  |
| target | n | r (DARKO) | r (carry-forward RAPM) | MAE (DARKO) | MAE (carry-forward) | sd_target |
| next season only | 7014 | 0.369 | 0.379 | 1.634 | 1.683 | 1.906 |
| 2-season RAPM | 7014 | 0.410 | 0.418 | 1.466 | 1.526 | 1.621 |
| 3-season RAPM | 7014 | 0.437 | 0.442 | 1.387 | 1.455 | 1.494 |

&#10;</div>

Two readings, both worth stating plainly:

- **Most of the “modest” forward-r is target noise.** Holding the
  projection and the population fixed and only widening the target
  window lifts the correlation materially (≈0.37 → ≈0.44 from a
  one-season to a three-season target). The projection did not improve;
  the yardstick got less noisy.
- **The projection is not beating simple persistence on rank.** Carrying
  season-*t* RAPM forward unchanged correlates with every target about
  as well as the DARKO projection does (marginally better, in fact).
  Where the projection does earn its keep is **level**: its MAE is lower
  against every target, which is what shrinkage toward the aging-curve
  mean buys. Treat `darko_projected_rating` as a better-calibrated
  magnitude, not a better ordering — and the gap to persistence is the
  honest measure of what the Kalman step is currently adding.

**Concurrent validity + the publish floors.** The engines are gated
against the published Ryan Davis single-season RAPM oracle at build
time: over the 14 covered seasons (2010–2023) `r(rapm, oracle)` runs
0.948–0.990 and beats the minutes-played baseline by **+0.60 to +0.75
correlation points** (the registry previously recorded this as “~10%”,
which understated it). Those observations, with the five internal ones,
are now frozen as **seven publish-blocking floors** in
`models/REGISTRY.md` and `nba_model_publish/gates.py`; the gate runs on
every `impact` invocation and writes its report into the card sidecar
under `publish_gates`. Dunks & Threes EPM is reported but deliberately
not gated — two covered seasons is too thin a base to set a floor from.

## Results

<div id="zimsdkwwtq" style="padding-left:0px;padding-right:0px;padding-top:10px;padding-bottom:10px;overflow-x:auto;overflow-y:auto;width:auto;height:auto;">
<style>
#zimsdkwwtq table {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', 'Fira Sans', 'Droid Sans', Arial, sans-serif;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }
&#10;#zimsdkwwtq thead, tbody, tfoot, tr, td, th { border-style: none; }
 tr { background-color: transparent; }
#zimsdkwwtq p { margin: 0; padding: 0; }
 #zimsdkwwtq .gt_table { display: table; border-collapse: collapse; line-height: normal; margin-left: auto; margin-right: auto; color: #333333; font-size: 16px; font-weight: normal; font-style: normal; background-color: #FFFFFF; width: auto; border-top-style: solid; border-top-width: 2px; border-top-color: #A8A8A8; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #A8A8A8; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; }
 #zimsdkwwtq .gt_caption { padding-top: 4px; padding-bottom: 4px; }
 #zimsdkwwtq .gt_title { color: #333333; font-size: 125%; font-weight: initial; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; border-bottom-color: #FFFFFF; border-bottom-width: 0; }
 #zimsdkwwtq .gt_subtitle { color: #333333; font-size: 85%; font-weight: initial; padding-top: 3px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; border-top-color: #FFFFFF; border-top-width: 0; }
 #zimsdkwwtq .gt_heading { background-color: #FFFFFF; text-align: center; border-bottom-color: #FFFFFF; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #zimsdkwwtq .gt_bottom_border { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #zimsdkwwtq .gt_col_headings { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; }
 #zimsdkwwtq .gt_col_heading { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; padding-left: 5px; padding-right: 5px; overflow-x: hidden; }
 #zimsdkwwtq .gt_column_spanner_outer { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: normal; text-transform: inherit; padding-top: 0; padding-bottom: 0; padding-left: 4px; padding-right: 4px; }
 #zimsdkwwtq .gt_column_spanner_outer:first-child { padding-left: 0; }
 #zimsdkwwtq .gt_column_spanner_outer:last-child { padding-right: 0; }
 #zimsdkwwtq .gt_column_spanner { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: bottom; padding-top: 5px; padding-bottom: 5px; overflow-x: hidden; display: inline-block; width: 100%; }
 #zimsdkwwtq .gt_spanner_row { border-bottom-style: hidden; }
 #zimsdkwwtq .gt_group_heading { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; text-align: left; }
 #zimsdkwwtq .gt_empty_group_heading { padding: 0.5px; color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; vertical-align: middle; }
 #zimsdkwwtq .gt_from_md> :first-child { margin-top: 0; }
 #zimsdkwwtq .gt_from_md> :last-child { margin-bottom: 0; }
 #zimsdkwwtq .gt_row { padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; margin: 10px; border-top-style: solid; border-top-width: 1px; border-top-color: #D3D3D3; border-left-style: none; border-left-width: 1px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 1px; border-right-color: #D3D3D3; vertical-align: middle; overflow-x: hidden; }
 #zimsdkwwtq .gt_stub { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; }
 #zimsdkwwtq .gt_indent_1 { text-indent: 5px; }
 #zimsdkwwtq .gt_indent_2 { text-indent: calc(5px * 2); }
 #zimsdkwwtq .gt_indent_3 { text-indent: calc(5px * 3); }
 #zimsdkwwtq .gt_indent_4 { text-indent: calc(5px * 4); }
 #zimsdkwwtq .gt_indent_5 { text-indent: calc(5px * 5); }
 #zimsdkwwtq .gt_stub_row_group { color: #333333; background-color: #FFFFFF; font-size: 100%; font-weight: initial; text-transform: inherit; border-right-style: solid; border-right-width: 2px; border-right-color: #D3D3D3; padding-left: 5px; padding-right: 5px; vertical-align: top; }
 #zimsdkwwtq .gt_row_group_first td { border-top-width: 2px; }
 #zimsdkwwtq .gt_row_group_first th { border-top-width: 2px; }
 #zimsdkwwtq .gt_striped { color: #333333; background-color: #F4F4F4; }
 #zimsdkwwtq .gt_table_body { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #zimsdkwwtq .gt_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #zimsdkwwtq .gt_first_summary_row { border-top-style: solid; border-top-width: 2px; border-top-color: #D3D3D3; }
 #zimsdkwwtq .gt_last_summary_row_top { border-bottom-style: solid; border-bottom-width: 2px; border-bottom-color: #D3D3D3; }
 #zimsdkwwtq .gt_grand_summary_row { color: #333333; background-color: #FFFFFF; text-transform: inherit; padding-top: 8px; padding-bottom: 8px; padding-left: 5px; padding-right: 5px; }
 #zimsdkwwtq .gt_first_grand_summary_row_bottom { border-top-style: double; border-top-width: 6px; border-top-color: #D3D3D3; }
 #zimsdkwwtq .gt_last_grand_summary_row_top { border-bottom-style: double; border-bottom-width: 6px; border-bottom-color: #D3D3D3; }
 #zimsdkwwtq .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #zimsdkwwtq .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #zimsdkwwtq .gt_left { text-align: left; }
 #zimsdkwwtq .gt_center { text-align: center; }
 #zimsdkwwtq .gt_right { text-align: right; font-variant-numeric: tabular-nums; }
 #zimsdkwwtq .gt_font_normal { font-weight: normal; }
 #zimsdkwwtq .gt_font_bold { font-weight: bold; }
 #zimsdkwwtq .gt_font_italic { font-style: italic; }
 #zimsdkwwtq .gt_super { font-size: 65%; }
 #zimsdkwwtq .gt_footnotes { color: font-color(#FFFFFF); background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #zimsdkwwtq .gt_footnote { margin: 0px; font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; }
 #zimsdkwwtq .gt_sourcenotes { color: #333333; background-color: #FFFFFF; border-bottom-style: none; border-bottom-width: 2px; border-bottom-color: #D3D3D3; border-left-style: none; border-left-width: 2px; border-left-color: #D3D3D3; border-right-style: none; border-right-width: 2px; border-right-color: #D3D3D3; }
 #zimsdkwwtq .gt_sourcenote { font-size: 90%; padding-top: 4px; padding-bottom: 4px; padding-left: 5px; padding-right: 5px; text-align: left; }
 #zimsdkwwtq .gt_footnote_marks { font-size: 75%; vertical-align: 0.4em; position: initial; }
 #zimsdkwwtq .gt_asterisk { font-size: 100%; vertical-align: 0; }
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

**Resolved (2026-09-01, PR \#NBA_PR):**

- **Numeric publish floors are encoded** — seven gates in
  `nba_model_publish/gates.py`, each floor strictly below the value
  observed on the 2026-07-29 release across all 30 seasons, evaluated on
  every build and recorded in the card sidecar. The table (floor,
  observation, what it catches) lives in `models/REGISTRY.md`.
- **The SPM coefficient vector ships** as the additive
  `nba_player_impact_spm_coefficients.json` sidecar, and the Attribution
  section above now shows real coefficient importance from it.
- **DARKO ceiling quantified** — the multi-season blended-target
  comparison above separates projection error from target noise, and
  states the projection’s standing against a carry-forward baseline.

Still open:

- **Uncertainty** — no engine ships an interval yet, and a prototype run
  says that matters more than it sounds. Resampling **whole games** with
  replacement (never rows — a row bootstrap on possession data
  understates the spread by the design-effect factor) over the 2023-24
  regular season (1,230 games, 242,618 possessions, 25 replicates, 16.3
  s per RAPM refit) gives a **median RAPM standard error of 2.60 per
  100** for players with ≥1,000 possessions, against a cross-sectional
  **RAPM standard deviation of 1.41** in that same group. The resample
  spread is wider than the entire spread of the metric — consistent with
  the modest year-over-year reliability above, and a caution against
  reading single-season RAPM gaps as differences between players. Two
  honest caveats before that number is treated as a published interval:
  25 replicates estimate an SE to only ~15% relative precision, and a
  game-level resample also perturbs each player’s own sample size, so it
  is a deliberately **conservative** bound rather than a calibrated
  posterior. Shipping it means B ≥ 200 (~55 min per season-type,
  affordable per publish for recent seasons, not for a 30-season
  backfill in one pass), an additive `rapm_se` column, and a floor on
  the interval’s own stability.
- **PlayIn season type is unsupported** by design; revisit if the sample
  ever justifies it.
