"""Typed schema declarations for every published NBA stats dataset (spec D39).

These declare the SCHEMA, not the rows. ``polars_schema()`` converts a model to
a ``pl.Schema`` asserted frame-level at the write chokepoint
(``nba_data_build.io.write_release_formats``); row-level pydantic validation over
a multi-million-row pbp frame is a performance trap and is not the build path.

Generated from the real published parquets (latest season per release tag) plus
the committed schedule-master artifacts, then kept by hand.

``game_id`` is ``str`` everywhere: NBA stats game ids carry the
"00" league prefix ("0022300001") and an int round-trip drops the padding, so the id is
pinned Utf8 at every boundary (see ``master.py``). Numeric entity ids
(``team_id``, ``person_id``/``player_id``) are ``int`` (Int64).

Strict mode is deliberate: without it pydantic coerces "1610612737" to int and
5 to 5.0, which is exactly the id-dtype bug class these repos exist to avoid.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import polars as pl
from pydantic import BaseModel, ConfigDict

_PL_TYPES: dict[type, pl.DataType] = {
    str: pl.Utf8,
    int: pl.Int64,
    float: pl.Float64,
    bool: pl.Boolean,
    date: pl.Date,
    datetime: pl.Datetime('us'),
}


class NbaStatsDataset(BaseModel):
    """Base for every dataset model: strict (no silent type coercion)."""

    model_config = ConfigDict(strict=True)


class Standings(NbaStatsDataset):
    """`standings` — declared from the latest published/committed parquet."""

    league_id: Optional[str] = None
    season_id: Optional[str] = None
    team_id: Optional[int] = None
    team_city: Optional[str] = None
    team_name: Optional[str] = None
    team_slug: Optional[str] = None
    conference: Optional[str] = None
    conference_record: Optional[str] = None
    playoff_rank: Optional[int] = None
    clinch_indicator: Optional[str] = None
    division: Optional[str] = None
    division_record: Optional[str] = None
    division_rank: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    win_pct: Optional[float] = None
    league_rank: Optional[int] = None
    record: Optional[str] = None
    home: Optional[str] = None
    road: Optional[str] = None
    l10: Optional[str] = None
    last10_home: Optional[str] = None
    last10_road: Optional[str] = None
    ot: Optional[str] = None
    three_pts_or_less: Optional[str] = None
    ten_pts_or_more: Optional[str] = None
    long_home_streak: Optional[int] = None
    str_long_home_streak: Optional[str] = None
    long_road_streak: Optional[int] = None
    str_long_road_streak: Optional[str] = None
    long_win_streak: Optional[int] = None
    long_loss_streak: Optional[int] = None
    current_home_streak: Optional[int] = None
    str_current_home_streak: Optional[str] = None
    current_road_streak: Optional[int] = None
    str_current_road_streak: Optional[str] = None
    current_streak: Optional[int] = None
    str_current_streak: Optional[str] = None
    conference_games_back: Optional[float] = None
    division_games_back: Optional[float] = None
    clinched_conference_title: Optional[int] = None
    clinched_division_title: Optional[int] = None
    clinched_playoff_birth: Optional[int] = None
    clinched_play_in: Optional[int] = None
    eliminated_conference: Optional[int] = None
    eliminated_division: Optional[int] = None
    ahead_at_half: Optional[str] = None
    behind_at_half: Optional[str] = None
    tied_at_half: Optional[str] = None
    ahead_at_third: Optional[str] = None
    behind_at_third: Optional[str] = None
    tied_at_third: Optional[str] = None
    score100_pts: Optional[str] = None
    opp_score100_pts: Optional[str] = None
    opp_over500: Optional[str] = None
    lead_in_fgpct: Optional[str] = None
    lead_in_reb: Optional[str] = None
    fewer_turnovers: Optional[str] = None
    points_pg: Optional[float] = None
    opp_points_pg: Optional[float] = None
    diff_points_pg: Optional[float] = None
    vs_east: Optional[str] = None
    vs_atlantic: Optional[str] = None
    vs_central: Optional[str] = None
    vs_southeast: Optional[str] = None
    vs_west: Optional[str] = None
    vs_northwest: Optional[str] = None
    vs_pacific: Optional[str] = None
    vs_southwest: Optional[str] = None
    jan: Optional[str] = None
    feb: Optional[str] = None
    mar: Optional[str] = None
    apr: Optional[str] = None
    may: Optional[str] = None
    jun: Optional[str] = None
    jul: Optional[str] = None
    aug: Optional[str] = None
    sep: Optional[str] = None
    oct: Optional[str] = None
    nov: Optional[str] = None
    dec: Optional[str] = None
    score_80_plus: Optional[str] = None
    opp_score_80_plus: Optional[str] = None
    score_below_80: Optional[str] = None
    opp_score_below_80: Optional[str] = None
    total_points: Optional[int] = None
    opp_total_points: Optional[int] = None
    diff_total_points: Optional[int] = None
    league_games_back: Optional[float] = None
    playoff_seeding: Optional[int] = None
    clinched_post_season: Optional[int] = None
    neutral: Optional[str] = None
    season: Optional[int] = None
    season_type: Optional[str] = None


class PlayerSeasonStats(NbaStatsDataset):
    """`player_season_stats` — declared from the latest published/committed parquet."""

    player_id: Optional[int] = None
    player_name: Optional[str] = None
    nickname: Optional[str] = None
    team_id: Optional[int] = None
    team_abbreviation: Optional[str] = None
    age: Optional[float] = None
    gp: Optional[int] = None
    w: Optional[int] = None
    l: Optional[int] = None
    w_pct: Optional[float] = None
    min: Optional[float] = None
    e_off_rating: Optional[float] = None
    off_rating: Optional[float] = None
    sp_work_off_rating: Optional[float] = None
    e_def_rating: Optional[float] = None
    def_rating: Optional[float] = None
    sp_work_def_rating: Optional[float] = None
    e_net_rating: Optional[float] = None
    net_rating: Optional[float] = None
    sp_work_net_rating: Optional[float] = None
    ast_pct: Optional[float] = None
    ast_to: Optional[float] = None
    ast_ratio: Optional[float] = None
    oreb_pct: Optional[float] = None
    dreb_pct: Optional[float] = None
    reb_pct: Optional[float] = None
    tm_tov_pct: Optional[float] = None
    e_tov_pct: Optional[float] = None
    efg_pct: Optional[float] = None
    ts_pct: Optional[float] = None
    usg_pct: Optional[float] = None
    e_usg_pct: Optional[float] = None
    e_pace: Optional[float] = None
    pace: Optional[float] = None
    pace_per40: Optional[float] = None
    sp_work_pace: Optional[float] = None
    pie: Optional[float] = None
    poss: Optional[int] = None
    fgm: Optional[float] = None
    fga: Optional[float] = None
    fgm_pg: Optional[float] = None
    fga_pg: Optional[float] = None
    fg_pct: Optional[float] = None
    gp_rank: Optional[int] = None
    w_rank: Optional[int] = None
    l_rank: Optional[int] = None
    w_pct_rank: Optional[int] = None
    min_rank: Optional[int] = None
    e_off_rating_rank: Optional[int] = None
    off_rating_rank: Optional[int] = None
    sp_work_off_rating_rank: Optional[int] = None
    e_def_rating_rank: Optional[int] = None
    def_rating_rank: Optional[int] = None
    sp_work_def_rating_rank: Optional[int] = None
    e_net_rating_rank: Optional[int] = None
    net_rating_rank: Optional[int] = None
    sp_work_net_rating_rank: Optional[int] = None
    ast_pct_rank: Optional[int] = None
    ast_to_rank: Optional[int] = None
    ast_ratio_rank: Optional[int] = None
    oreb_pct_rank: Optional[int] = None
    dreb_pct_rank: Optional[int] = None
    reb_pct_rank: Optional[int] = None
    tm_tov_pct_rank: Optional[int] = None
    e_tov_pct_rank: Optional[int] = None
    efg_pct_rank: Optional[int] = None
    ts_pct_rank: Optional[int] = None
    usg_pct_rank: Optional[int] = None
    e_usg_pct_rank: Optional[int] = None
    e_pace_rank: Optional[int] = None
    pace_rank: Optional[int] = None
    sp_work_pace_rank: Optional[int] = None
    pie_rank: Optional[int] = None
    fgm_rank: Optional[int] = None
    fga_rank: Optional[int] = None
    fgm_pg_rank: Optional[int] = None
    fga_pg_rank: Optional[int] = None
    fg_pct_rank: Optional[int] = None
    team_count: Optional[int] = None
    season: Optional[int] = None
    season_type: Optional[str] = None
    measure_type: Optional[str] = None
    per_mode: Optional[str] = None
    fg3m: Optional[float] = None
    fg3a: Optional[float] = None
    fg3_pct: Optional[float] = None
    ftm: Optional[float] = None
    fta: Optional[float] = None
    ft_pct: Optional[float] = None
    oreb: Optional[float] = None
    dreb: Optional[float] = None
    reb: Optional[float] = None
    ast: Optional[float] = None
    tov: Optional[float] = None
    stl: Optional[float] = None
    blk: Optional[float] = None
    blka: Optional[float] = None
    pf: Optional[float] = None
    pfd: Optional[float] = None
    pts: Optional[float] = None
    plus_minus: Optional[float] = None
    nba_fantasy_pts: Optional[float] = None
    dd2: Optional[int] = None
    td3: Optional[int] = None
    wnba_fantasy_pts: Optional[float] = None
    fg3m_rank: Optional[int] = None
    fg3a_rank: Optional[int] = None
    fg3_pct_rank: Optional[int] = None
    ftm_rank: Optional[int] = None
    fta_rank: Optional[int] = None
    ft_pct_rank: Optional[int] = None
    oreb_rank: Optional[int] = None
    dreb_rank: Optional[int] = None
    reb_rank: Optional[int] = None
    ast_rank: Optional[int] = None
    tov_rank: Optional[int] = None
    stl_rank: Optional[int] = None
    blk_rank: Optional[int] = None
    blka_rank: Optional[int] = None
    pf_rank: Optional[int] = None
    pfd_rank: Optional[int] = None
    pts_rank: Optional[int] = None
    plus_minus_rank: Optional[int] = None
    nba_fantasy_pts_rank: Optional[int] = None
    dd2_rank: Optional[int] = None
    td3_rank: Optional[int] = None
    wnba_fantasy_pts_rank: Optional[int] = None
    pct_dreb: Optional[float] = None
    pct_stl: Optional[float] = None
    pct_blk: Optional[float] = None
    opp_pts_off_tov: Optional[float] = None
    opp_pts_2nd_chance: Optional[float] = None
    opp_pts_fb: Optional[float] = None
    opp_pts_paint: Optional[float] = None
    def_ws: Optional[float] = None
    def_ws_raw: Optional[float] = None
    pct_dreb_rank: Optional[int] = None
    pct_stl_rank: Optional[int] = None
    pct_blk_rank: Optional[int] = None
    opp_pts_off_tov_rank: Optional[int] = None
    opp_pts_2nd_chance_rank: Optional[int] = None
    opp_pts_fb_rank: Optional[int] = None
    opp_pts_paint_rank: Optional[int] = None
    def_ws_rank: Optional[int] = None
    pts_off_tov: Optional[float] = None
    pts_2nd_chance: Optional[float] = None
    pts_fb: Optional[float] = None
    pts_paint: Optional[float] = None
    pts_off_tov_rank: Optional[int] = None
    pts_2nd_chance_rank: Optional[int] = None
    pts_fb_rank: Optional[int] = None
    pts_paint_rank: Optional[int] = None
    pct_fga_2pt: Optional[float] = None
    pct_fga_3pt: Optional[float] = None
    pct_pts_2pt: Optional[float] = None
    pct_pts_2pt_mr: Optional[float] = None
    pct_pts_3pt: Optional[float] = None
    pct_pts_fb: Optional[float] = None
    pct_pts_ft: Optional[float] = None
    pct_pts_off_tov: Optional[float] = None
    pct_pts_paint: Optional[float] = None
    pct_ast_2pm: Optional[float] = None
    pct_uast_2pm: Optional[float] = None
    pct_ast_3pm: Optional[float] = None
    pct_uast_3pm: Optional[float] = None
    pct_ast_fgm: Optional[float] = None
    pct_uast_fgm: Optional[float] = None
    pct_fga_2pt_rank: Optional[int] = None
    pct_fga_3pt_rank: Optional[int] = None
    pct_pts_2pt_rank: Optional[int] = None
    pct_pts_2pt_mr_rank: Optional[int] = None
    pct_pts_3pt_rank: Optional[int] = None
    pct_pts_fb_rank: Optional[int] = None
    pct_pts_ft_rank: Optional[int] = None
    pct_pts_off_tov_rank: Optional[int] = None
    pct_pts_paint_rank: Optional[int] = None
    pct_ast_2pm_rank: Optional[int] = None
    pct_uast_2pm_rank: Optional[int] = None
    pct_ast_3pm_rank: Optional[int] = None
    pct_uast_3pm_rank: Optional[int] = None
    pct_ast_fgm_rank: Optional[int] = None
    pct_uast_fgm_rank: Optional[int] = None
    pct_fgm: Optional[float] = None
    pct_fga: Optional[float] = None
    pct_fg3m: Optional[float] = None
    pct_fg3a: Optional[float] = None
    pct_ftm: Optional[float] = None
    pct_fta: Optional[float] = None
    pct_oreb: Optional[float] = None
    pct_reb: Optional[float] = None
    pct_ast: Optional[float] = None
    pct_tov: Optional[float] = None
    pct_blka: Optional[float] = None
    pct_pf: Optional[float] = None
    pct_pfd: Optional[float] = None
    pct_pts: Optional[float] = None
    pct_fgm_rank: Optional[int] = None
    pct_fga_rank: Optional[int] = None
    pct_fg3m_rank: Optional[int] = None
    pct_fg3a_rank: Optional[int] = None
    pct_ftm_rank: Optional[int] = None
    pct_fta_rank: Optional[int] = None
    pct_oreb_rank: Optional[int] = None
    pct_reb_rank: Optional[int] = None
    pct_ast_rank: Optional[int] = None
    pct_tov_rank: Optional[int] = None
    pct_blka_rank: Optional[int] = None
    pct_pf_rank: Optional[int] = None
    pct_pfd_rank: Optional[int] = None
    pct_pts_rank: Optional[int] = None


class TeamSeasonStats(NbaStatsDataset):
    """`team_season_stats` — declared from the latest published/committed parquet."""

    team_id: Optional[int] = None
    team_name: Optional[str] = None
    gp: Optional[int] = None
    w: Optional[int] = None
    l: Optional[int] = None
    w_pct: Optional[float] = None
    min: Optional[float] = None
    e_off_rating: Optional[float] = None
    off_rating: Optional[float] = None
    e_def_rating: Optional[float] = None
    def_rating: Optional[float] = None
    e_net_rating: Optional[float] = None
    net_rating: Optional[float] = None
    ast_pct: Optional[float] = None
    ast_to: Optional[float] = None
    ast_ratio: Optional[float] = None
    oreb_pct: Optional[float] = None
    dreb_pct: Optional[float] = None
    reb_pct: Optional[float] = None
    tm_tov_pct: Optional[float] = None
    efg_pct: Optional[float] = None
    ts_pct: Optional[float] = None
    e_pace: Optional[float] = None
    pace: Optional[float] = None
    pace_per40: Optional[float] = None
    poss: Optional[int] = None
    pie: Optional[float] = None
    gp_rank: Optional[int] = None
    w_rank: Optional[int] = None
    l_rank: Optional[int] = None
    w_pct_rank: Optional[int] = None
    min_rank: Optional[int] = None
    off_rating_rank: Optional[int] = None
    def_rating_rank: Optional[int] = None
    net_rating_rank: Optional[int] = None
    ast_pct_rank: Optional[int] = None
    ast_to_rank: Optional[int] = None
    ast_ratio_rank: Optional[int] = None
    oreb_pct_rank: Optional[int] = None
    dreb_pct_rank: Optional[int] = None
    reb_pct_rank: Optional[int] = None
    tm_tov_pct_rank: Optional[int] = None
    efg_pct_rank: Optional[int] = None
    ts_pct_rank: Optional[int] = None
    pace_rank: Optional[int] = None
    pie_rank: Optional[int] = None
    season: Optional[int] = None
    season_type: Optional[str] = None
    measure_type: Optional[str] = None
    per_mode: Optional[str] = None
    fgm: Optional[float] = None
    fga: Optional[float] = None
    fg_pct: Optional[float] = None
    fg3m: Optional[float] = None
    fg3a: Optional[float] = None
    fg3_pct: Optional[float] = None
    ftm: Optional[float] = None
    fta: Optional[float] = None
    ft_pct: Optional[float] = None
    oreb: Optional[float] = None
    dreb: Optional[float] = None
    reb: Optional[float] = None
    ast: Optional[float] = None
    tov: Optional[float] = None
    stl: Optional[float] = None
    blk: Optional[float] = None
    blka: Optional[float] = None
    pf: Optional[float] = None
    pfd: Optional[float] = None
    pts: Optional[float] = None
    plus_minus: Optional[float] = None
    fgm_rank: Optional[int] = None
    fga_rank: Optional[int] = None
    fg_pct_rank: Optional[int] = None
    fg3m_rank: Optional[int] = None
    fg3a_rank: Optional[int] = None
    fg3_pct_rank: Optional[int] = None
    ftm_rank: Optional[int] = None
    fta_rank: Optional[int] = None
    ft_pct_rank: Optional[int] = None
    oreb_rank: Optional[int] = None
    dreb_rank: Optional[int] = None
    reb_rank: Optional[int] = None
    ast_rank: Optional[int] = None
    tov_rank: Optional[int] = None
    stl_rank: Optional[int] = None
    blk_rank: Optional[int] = None
    blka_rank: Optional[int] = None
    pf_rank: Optional[int] = None
    pfd_rank: Optional[int] = None
    pts_rank: Optional[int] = None
    plus_minus_rank: Optional[int] = None
    opp_pts_off_tov: Optional[float] = None
    opp_pts_2nd_chance: Optional[float] = None
    opp_pts_fb: Optional[float] = None
    opp_pts_paint: Optional[float] = None
    opp_pts_off_tov_rank: Optional[int] = None
    opp_pts_2nd_chance_rank: Optional[int] = None
    opp_pts_fb_rank: Optional[int] = None
    opp_pts_paint_rank: Optional[int] = None
    pts_off_tov: Optional[float] = None
    pts_2nd_chance: Optional[float] = None
    pts_fb: Optional[float] = None
    pts_paint: Optional[float] = None
    pts_off_tov_rank: Optional[int] = None
    pts_2nd_chance_rank: Optional[int] = None
    pts_fb_rank: Optional[int] = None
    pts_paint_rank: Optional[int] = None
    opp_fgm: Optional[float] = None
    opp_fga: Optional[float] = None
    opp_fg_pct: Optional[float] = None
    opp_fg3m: Optional[float] = None
    opp_fg3a: Optional[float] = None
    opp_fg3_pct: Optional[float] = None
    opp_ftm: Optional[float] = None
    opp_fta: Optional[float] = None
    opp_ft_pct: Optional[float] = None
    opp_oreb: Optional[float] = None
    opp_dreb: Optional[float] = None
    opp_reb: Optional[float] = None
    opp_ast: Optional[float] = None
    opp_tov: Optional[float] = None
    opp_stl: Optional[float] = None
    opp_blk: Optional[float] = None
    opp_blka: Optional[float] = None
    opp_pf: Optional[float] = None
    opp_pfd: Optional[float] = None
    opp_pts: Optional[float] = None
    opp_fgm_rank: Optional[int] = None
    opp_fga_rank: Optional[int] = None
    opp_fg_pct_rank: Optional[int] = None
    opp_fg3m_rank: Optional[int] = None
    opp_fg3a_rank: Optional[int] = None
    opp_fg3_pct_rank: Optional[int] = None
    opp_ftm_rank: Optional[int] = None
    opp_fta_rank: Optional[int] = None
    opp_ft_pct_rank: Optional[int] = None
    opp_oreb_rank: Optional[int] = None
    opp_dreb_rank: Optional[int] = None
    opp_reb_rank: Optional[int] = None
    opp_ast_rank: Optional[int] = None
    opp_tov_rank: Optional[int] = None
    opp_stl_rank: Optional[int] = None
    opp_blk_rank: Optional[int] = None
    opp_blka_rank: Optional[int] = None
    opp_pf_rank: Optional[int] = None
    opp_pfd_rank: Optional[int] = None
    opp_pts_rank: Optional[int] = None
    pct_fga_2pt: Optional[float] = None
    pct_fga_3pt: Optional[float] = None
    pct_pts_2pt: Optional[float] = None
    pct_pts_2pt_mr: Optional[float] = None
    pct_pts_3pt: Optional[float] = None
    pct_pts_fb: Optional[float] = None
    pct_pts_ft: Optional[float] = None
    pct_pts_off_tov: Optional[float] = None
    pct_pts_paint: Optional[float] = None
    pct_ast_2pm: Optional[float] = None
    pct_uast_2pm: Optional[float] = None
    pct_ast_3pm: Optional[float] = None
    pct_uast_3pm: Optional[float] = None
    pct_ast_fgm: Optional[float] = None
    pct_uast_fgm: Optional[float] = None
    pct_fga_2pt_rank: Optional[int] = None
    pct_fga_3pt_rank: Optional[int] = None
    pct_pts_2pt_rank: Optional[int] = None
    pct_pts_2pt_mr_rank: Optional[int] = None
    pct_pts_3pt_rank: Optional[int] = None
    pct_pts_fb_rank: Optional[int] = None
    pct_pts_ft_rank: Optional[int] = None
    pct_pts_off_tov_rank: Optional[int] = None
    pct_pts_paint_rank: Optional[int] = None
    pct_ast_2pm_rank: Optional[int] = None
    pct_uast_2pm_rank: Optional[int] = None
    pct_ast_3pm_rank: Optional[int] = None
    pct_uast_3pm_rank: Optional[int] = None
    pct_ast_fgm_rank: Optional[int] = None
    pct_uast_fgm_rank: Optional[int] = None


class Lineups(NbaStatsDataset):
    """`lineups` — declared from the latest published/committed parquet."""

    group_set: Optional[str] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    team_id: Optional[int] = None
    team_abbreviation: Optional[str] = None
    gp: Optional[int] = None
    w: Optional[int] = None
    l: Optional[int] = None
    w_pct: Optional[float] = None
    min: Optional[float] = None
    e_off_rating: Optional[float] = None
    off_rating: Optional[float] = None
    e_def_rating: Optional[float] = None
    def_rating: Optional[float] = None
    e_net_rating: Optional[float] = None
    net_rating: Optional[float] = None
    ast_pct: Optional[float] = None
    ast_to: Optional[float] = None
    ast_ratio: Optional[float] = None
    oreb_pct: Optional[float] = None
    dreb_pct: Optional[float] = None
    reb_pct: Optional[float] = None
    tm_tov_pct: Optional[float] = None
    efg_pct: Optional[float] = None
    ts_pct: Optional[float] = None
    e_pace: Optional[float] = None
    pace: Optional[float] = None
    pace_per40: Optional[float] = None
    poss: Optional[int] = None
    pie: Optional[float] = None
    gp_rank: Optional[int] = None
    w_rank: Optional[int] = None
    l_rank: Optional[int] = None
    w_pct_rank: Optional[int] = None
    min_rank: Optional[int] = None
    off_rating_rank: Optional[int] = None
    def_rating_rank: Optional[int] = None
    net_rating_rank: Optional[int] = None
    ast_pct_rank: Optional[int] = None
    ast_to_rank: Optional[int] = None
    ast_ratio_rank: Optional[int] = None
    oreb_pct_rank: Optional[int] = None
    dreb_pct_rank: Optional[int] = None
    reb_pct_rank: Optional[int] = None
    tm_tov_pct_rank: Optional[int] = None
    efg_pct_rank: Optional[int] = None
    ts_pct_rank: Optional[int] = None
    pace_rank: Optional[int] = None
    pie_rank: Optional[int] = None
    sum_time_played: Optional[int] = None
    season: Optional[int] = None
    season_type: Optional[str] = None
    measure_type: Optional[str] = None
    per_mode: Optional[str] = None
    fgm: Optional[float] = None
    fga: Optional[float] = None
    fg_pct: Optional[float] = None
    fg3m: Optional[float] = None
    fg3a: Optional[float] = None
    fg3_pct: Optional[float] = None
    ftm: Optional[float] = None
    fta: Optional[float] = None
    ft_pct: Optional[float] = None
    oreb: Optional[float] = None
    dreb: Optional[float] = None
    reb: Optional[float] = None
    ast: Optional[float] = None
    tov: Optional[float] = None
    stl: Optional[float] = None
    blk: Optional[float] = None
    blka: Optional[float] = None
    pf: Optional[float] = None
    pfd: Optional[float] = None
    pts: Optional[float] = None
    plus_minus: Optional[float] = None
    fgm_rank: Optional[int] = None
    fga_rank: Optional[int] = None
    fg_pct_rank: Optional[int] = None
    fg3m_rank: Optional[int] = None
    fg3a_rank: Optional[int] = None
    fg3_pct_rank: Optional[int] = None
    ftm_rank: Optional[int] = None
    fta_rank: Optional[int] = None
    ft_pct_rank: Optional[int] = None
    oreb_rank: Optional[int] = None
    dreb_rank: Optional[int] = None
    reb_rank: Optional[int] = None
    ast_rank: Optional[int] = None
    tov_rank: Optional[int] = None
    stl_rank: Optional[int] = None
    blk_rank: Optional[int] = None
    blka_rank: Optional[int] = None
    pf_rank: Optional[int] = None
    pfd_rank: Optional[int] = None
    pts_rank: Optional[int] = None
    plus_minus_rank: Optional[int] = None
    pts_off_tov: Optional[float] = None
    pts_2nd_chance: Optional[float] = None
    pts_fb: Optional[float] = None
    pts_paint: Optional[float] = None
    opp_pts_off_tov: Optional[float] = None
    opp_pts_2nd_chance: Optional[float] = None
    opp_pts_fb: Optional[float] = None
    opp_pts_paint: Optional[float] = None
    pts_off_tov_rank: Optional[int] = None
    pts_2nd_chance_rank: Optional[int] = None
    pts_fb_rank: Optional[int] = None
    pts_paint_rank: Optional[int] = None
    opp_pts_off_tov_rank: Optional[int] = None
    opp_pts_2nd_chance_rank: Optional[int] = None
    opp_pts_fb_rank: Optional[int] = None
    opp_pts_paint_rank: Optional[int] = None
    opp_fgm: Optional[float] = None
    opp_fga: Optional[float] = None
    opp_fg_pct: Optional[float] = None
    opp_fg3m: Optional[float] = None
    opp_fg3a: Optional[float] = None
    opp_fg3_pct: Optional[float] = None
    opp_ftm: Optional[float] = None
    opp_fta: Optional[float] = None
    opp_ft_pct: Optional[float] = None
    opp_oreb: Optional[float] = None
    opp_dreb: Optional[float] = None
    opp_reb: Optional[float] = None
    opp_ast: Optional[float] = None
    opp_tov: Optional[float] = None
    opp_stl: Optional[float] = None
    opp_blk: Optional[float] = None
    opp_blka: Optional[float] = None
    opp_pf: Optional[float] = None
    opp_pfd: Optional[float] = None
    opp_pts: Optional[float] = None
    opp_fgm_rank: Optional[int] = None
    opp_fga_rank: Optional[int] = None
    opp_fg_pct_rank: Optional[int] = None
    opp_fg3m_rank: Optional[int] = None
    opp_fg3a_rank: Optional[int] = None
    opp_fg3_pct_rank: Optional[int] = None
    opp_ftm_rank: Optional[int] = None
    opp_fta_rank: Optional[int] = None
    opp_ft_pct_rank: Optional[int] = None
    opp_oreb_rank: Optional[int] = None
    opp_dreb_rank: Optional[int] = None
    opp_reb_rank: Optional[int] = None
    opp_ast_rank: Optional[int] = None
    opp_tov_rank: Optional[int] = None
    opp_stl_rank: Optional[int] = None
    opp_blk_rank: Optional[int] = None
    opp_blka_rank: Optional[int] = None
    opp_pf_rank: Optional[int] = None
    opp_pfd_rank: Optional[int] = None
    opp_pts_rank: Optional[int] = None
    pct_fga_2pt: Optional[float] = None
    pct_fga_3pt: Optional[float] = None
    pct_pts_2pt: Optional[float] = None
    pct_pts_2pt_mr: Optional[float] = None
    pct_pts_3pt: Optional[float] = None
    pct_pts_fb: Optional[float] = None
    pct_pts_ft: Optional[float] = None
    pct_pts_off_tov: Optional[float] = None
    pct_pts_paint: Optional[float] = None
    pct_ast_2pm: Optional[float] = None
    pct_uast_2pm: Optional[float] = None
    pct_ast_3pm: Optional[float] = None
    pct_uast_3pm: Optional[float] = None
    pct_ast_fgm: Optional[float] = None
    pct_uast_fgm: Optional[float] = None
    pct_fga_2pt_rank: Optional[int] = None
    pct_fga_3pt_rank: Optional[int] = None
    pct_pts_2pt_rank: Optional[int] = None
    pct_pts_2pt_mr_rank: Optional[int] = None
    pct_pts_3pt_rank: Optional[int] = None
    pct_pts_fb_rank: Optional[int] = None
    pct_pts_ft_rank: Optional[int] = None
    pct_pts_off_tov_rank: Optional[int] = None
    pct_pts_paint_rank: Optional[int] = None
    pct_ast_2pm_rank: Optional[int] = None
    pct_uast_2pm_rank: Optional[int] = None
    pct_ast_3pm_rank: Optional[int] = None
    pct_uast_3pm_rank: Optional[int] = None
    pct_ast_fgm_rank: Optional[int] = None
    pct_uast_fgm_rank: Optional[int] = None


class Rosters(NbaStatsDataset):
    """`rosters` — declared from the latest published/committed parquet."""

    team_id: Optional[int] = None
    season: Optional[int] = None
    league_id: Optional[str] = None
    player: Optional[str] = None
    nickname: Optional[str] = None
    player_slug: Optional[str] = None
    num: Optional[str] = None
    position: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    birth_date: Optional[str] = None
    age: Optional[float] = None
    exp: Optional[str] = None
    school: Optional[str] = None
    player_id: Optional[int] = None
    how_acquired: Optional[str] = None
    season_type: Optional[str] = None


class Coaches(NbaStatsDataset):
    """`coaches` — declared from the latest published/committed parquet."""

    team_id: Optional[int] = None
    season: Optional[int] = None
    coach_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    coach_name: Optional[str] = None
    is_assistant: Optional[int] = None
    coach_type: Optional[str] = None
    sort_sequence: Optional[int] = None
    sub_sort_sequence: Optional[int] = None
    season_type: Optional[str] = None


class Schedules(NbaStatsDataset):
    """`schedules` — declared from the latest published/committed parquet."""

    season_id: Optional[str] = None
    team_id: Optional[int] = None
    team_abbreviation: Optional[str] = None
    team_name: Optional[str] = None
    game_id: Optional[str] = None
    game_date: Optional[str] = None
    matchup: Optional[str] = None
    wl: Optional[str] = None
    min: Optional[int] = None
    fgm: Optional[int] = None
    fga: Optional[int] = None
    fg_pct: Optional[float] = None
    fg3m: Optional[int] = None
    fg3a: Optional[int] = None
    fg3_pct: Optional[float] = None
    ftm: Optional[int] = None
    fta: Optional[int] = None
    ft_pct: Optional[float] = None
    oreb: Optional[int] = None
    dreb: Optional[int] = None
    reb: Optional[int] = None
    ast: Optional[int] = None
    stl: Optional[int] = None
    blk: Optional[int] = None
    tov: Optional[int] = None
    pf: Optional[int] = None
    pts: Optional[int] = None
    plus_minus: Optional[int] = None
    video_available: Optional[int] = None
    season: Optional[int] = None
    season_type: Optional[str] = None


class PlayerGameLogs(NbaStatsDataset):
    """`player_game_logs` — declared from the latest published/committed parquet."""

    season_id: Optional[str] = None
    team_id: Optional[int] = None
    team_abbreviation: Optional[str] = None
    team_name: Optional[str] = None
    game_id: Optional[str] = None
    game_date: Optional[str] = None
    matchup: Optional[str] = None
    wl: Optional[str] = None
    min: Optional[int] = None
    fgm: Optional[int] = None
    fga: Optional[int] = None
    fg_pct: Optional[float] = None
    fg3m: Optional[int] = None
    fg3a: Optional[int] = None
    fg3_pct: Optional[float] = None
    ftm: Optional[int] = None
    fta: Optional[int] = None
    ft_pct: Optional[float] = None
    oreb: Optional[int] = None
    dreb: Optional[int] = None
    reb: Optional[int] = None
    ast: Optional[int] = None
    stl: Optional[int] = None
    blk: Optional[int] = None
    tov: Optional[int] = None
    pf: Optional[int] = None
    pts: Optional[int] = None
    plus_minus: Optional[int] = None
    video_available: Optional[int] = None
    season: Optional[int] = None
    season_type: Optional[str] = None


class Pbp(NbaStatsDataset):
    """`pbp` — declared from the latest published/committed parquet."""

    action_number: Optional[int] = None
    clock: Optional[str] = None
    period: Optional[int] = None
    team_id: Optional[int] = None
    team_tricode: Optional[str] = None
    person_id: Optional[int] = None
    player_name: Optional[str] = None
    player_name_i: Optional[str] = None
    x_legacy: Optional[int] = None
    y_legacy: Optional[int] = None
    shot_distance: Optional[int] = None
    shot_result: Optional[str] = None
    is_field_goal: Optional[int] = None
    score_home: Optional[str] = None
    score_away: Optional[str] = None
    points_total: Optional[int] = None
    location: Optional[str] = None
    description: Optional[str] = None
    action_type: Optional[str] = None
    sub_type: Optional[str] = None
    video_available: Optional[int] = None
    shot_value: Optional[int] = None
    action_id: Optional[int] = None
    game_id: Optional[str] = None
    season: Optional[int] = None


class GameRosters(NbaStatsDataset):
    """`game_rosters` — declared from the latest published/committed parquet."""

    player_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    jersey_num: Optional[str] = None
    team_id: Optional[int] = None
    team_city: Optional[str] = None
    team_name: Optional[str] = None
    team_abbreviation: Optional[str] = None
    season: Optional[int] = None
    game_id: Optional[str] = None


class Officials(NbaStatsDataset):
    """`officials` — declared from the latest published/committed parquet."""

    official_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    jersey_num: Optional[str] = None
    season: Optional[int] = None
    game_id: Optional[str] = None


class PlayerBoxscores(NbaStatsDataset):
    """`player_boxscores` — declared from the latest published/committed parquet."""

    team_id: Optional[int] = None
    team_name: Optional[str] = None
    team_tricode: Optional[str] = None
    side: Optional[str] = None
    person_id: Optional[int] = None
    first_name: Optional[str] = None
    family_name: Optional[str] = None
    name_i: Optional[str] = None
    player_slug: Optional[str] = None
    position: Optional[str] = None
    comment: Optional[str] = None
    jersey_num: Optional[str] = None
    minutes: Optional[str] = None
    field_goals_made: Optional[int] = None
    field_goals_attempted: Optional[int] = None
    field_goals_percentage: Optional[float] = None
    three_pointers_made: Optional[int] = None
    three_pointers_attempted: Optional[int] = None
    three_pointers_percentage: Optional[float] = None
    free_throws_made: Optional[int] = None
    free_throws_attempted: Optional[int] = None
    free_throws_percentage: Optional[float] = None
    rebounds_offensive: Optional[int] = None
    rebounds_defensive: Optional[int] = None
    rebounds_total: Optional[int] = None
    assists: Optional[int] = None
    steals: Optional[int] = None
    blocks: Optional[int] = None
    turnovers: Optional[int] = None
    fouls_personal: Optional[int] = None
    points: Optional[int] = None
    plus_minus_points: Optional[float] = None
    game_id: Optional[str] = None
    season: Optional[int] = None


class TeamBoxscores(NbaStatsDataset):
    """`team_boxscores` — declared from the latest published/committed parquet."""

    team_id: Optional[int] = None
    team_name: Optional[str] = None
    team_tricode: Optional[str] = None
    side: Optional[str] = None
    minutes: Optional[str] = None
    field_goals_made: Optional[int] = None
    field_goals_attempted: Optional[int] = None
    field_goals_percentage: Optional[float] = None
    three_pointers_made: Optional[int] = None
    three_pointers_attempted: Optional[int] = None
    three_pointers_percentage: Optional[float] = None
    free_throws_made: Optional[int] = None
    free_throws_attempted: Optional[int] = None
    free_throws_percentage: Optional[float] = None
    rebounds_offensive: Optional[int] = None
    rebounds_defensive: Optional[int] = None
    rebounds_total: Optional[int] = None
    assists: Optional[int] = None
    steals: Optional[int] = None
    blocks: Optional[int] = None
    turnovers: Optional[int] = None
    fouls_personal: Optional[int] = None
    points: Optional[int] = None
    plus_minus_points: Optional[float] = None
    game_id: Optional[str] = None
    season: Optional[int] = None


class Shots(NbaStatsDataset):
    """`shots` — declared from the latest published/committed parquet."""

    game_id: Optional[str] = None
    season: Optional[int] = None
    period: Optional[int] = None
    clock: Optional[str] = None
    team_id: Optional[int] = None
    team_tricode: Optional[str] = None
    person_id: Optional[int] = None
    player_name: Optional[str] = None
    action_type: Optional[str] = None
    sub_type: Optional[str] = None
    shot_result: Optional[str] = None
    shot_value: Optional[int] = None
    shot_distance: Optional[int] = None
    x_legacy: Optional[int] = None
    y_legacy: Optional[int] = None
    description: Optional[str] = None
    score_home: Optional[str] = None
    score_away: Optional[str] = None


class ScheduleMaster(NbaStatsDataset):
    """`schedule_master` — declared from the latest published/committed parquet."""

    PBP: Optional[bool] = None
    arena_city: Optional[str] = None
    arena_name: Optional[str] = None
    arena_state: Optional[str] = None
    away_team_city: Optional[str] = None
    away_team_id: Optional[int] = None
    away_team_losses: Optional[int] = None
    away_team_name: Optional[str] = None
    away_team_score: Optional[int] = None
    away_team_seed: Optional[int] = None
    away_team_slug: Optional[str] = None
    away_team_time: Optional[str] = None
    away_team_tricode: Optional[str] = None
    away_team_wins: Optional[int] = None
    branch_link: Optional[str] = None
    day: Optional[str] = None
    game_code: Optional[str] = None
    game_date: Optional[str] = None
    game_date_est: Optional[str] = None
    game_date_time_est: Optional[str] = None
    game_date_time_utc: Optional[str] = None
    game_date_utc: Optional[str] = None
    game_id: Optional[str] = None
    game_label: Optional[str] = None
    game_sequence: Optional[int] = None
    game_status: Optional[int] = None
    game_status_text: Optional[str] = None
    game_sub_label: Optional[str] = None
    game_subtype: Optional[str] = None
    game_time_est: Optional[str] = None
    game_time_utc: Optional[str] = None
    home_team_city: Optional[str] = None
    home_team_id: Optional[int] = None
    home_team_losses: Optional[int] = None
    home_team_name: Optional[str] = None
    home_team_score: Optional[int] = None
    home_team_seed: Optional[int] = None
    home_team_slug: Optional[str] = None
    home_team_time: Optional[str] = None
    home_team_tricode: Optional[str] = None
    home_team_wins: Optional[int] = None
    if_necessary: Optional[str] = None
    in_game_rosters: Optional[bool] = None
    in_officials: Optional[bool] = None
    in_pbp: Optional[bool] = None
    in_player_boxscores: Optional[bool] = None
    in_team_boxscores: Optional[bool] = None
    is_neutral: Optional[bool] = None
    league_id: Optional[str] = None
    month_num: Optional[int] = None
    postponed_status: Optional[str] = None
    season: Optional[str] = None
    season_type_description: Optional[str] = None
    season_type_id: Optional[str] = None
    series_game_number: Optional[str] = None
    series_text: Optional[str] = None
    week_name: Optional[str] = None
    week_number: Optional[int] = None


class GamesInDataRepo(NbaStatsDataset):
    """`games_in_data_repo` — declared from the latest published/committed parquet."""

    PBP: Optional[bool] = None
    arena_city: Optional[str] = None
    arena_name: Optional[str] = None
    arena_state: Optional[str] = None
    away_team_city: Optional[str] = None
    away_team_id: Optional[int] = None
    away_team_losses: Optional[int] = None
    away_team_name: Optional[str] = None
    away_team_score: Optional[int] = None
    away_team_seed: Optional[int] = None
    away_team_slug: Optional[str] = None
    away_team_time: Optional[str] = None
    away_team_tricode: Optional[str] = None
    away_team_wins: Optional[int] = None
    branch_link: Optional[str] = None
    day: Optional[str] = None
    game_code: Optional[str] = None
    game_date: Optional[str] = None
    game_date_est: Optional[str] = None
    game_date_time_est: Optional[str] = None
    game_date_time_utc: Optional[str] = None
    game_date_utc: Optional[str] = None
    game_id: Optional[str] = None
    game_label: Optional[str] = None
    game_sequence: Optional[int] = None
    game_status: Optional[int] = None
    game_status_text: Optional[str] = None
    game_sub_label: Optional[str] = None
    game_subtype: Optional[str] = None
    game_time_est: Optional[str] = None
    game_time_utc: Optional[str] = None
    home_team_city: Optional[str] = None
    home_team_id: Optional[int] = None
    home_team_losses: Optional[int] = None
    home_team_name: Optional[str] = None
    home_team_score: Optional[int] = None
    home_team_seed: Optional[int] = None
    home_team_slug: Optional[str] = None
    home_team_time: Optional[str] = None
    home_team_tricode: Optional[str] = None
    home_team_wins: Optional[int] = None
    if_necessary: Optional[str] = None
    in_game_rosters: Optional[bool] = None
    in_officials: Optional[bool] = None
    in_pbp: Optional[bool] = None
    in_player_boxscores: Optional[bool] = None
    in_team_boxscores: Optional[bool] = None
    is_neutral: Optional[bool] = None
    league_id: Optional[str] = None
    month_num: Optional[int] = None
    postponed_status: Optional[str] = None
    season: Optional[str] = None
    season_type_description: Optional[str] = None
    season_type_id: Optional[str] = None
    series_game_number: Optional[str] = None
    series_text: Optional[str] = None
    week_name: Optional[str] = None
    week_number: Optional[int] = None

MODELS: dict[str, type[NbaStatsDataset]] = {
    "standings": Standings,
    "player_season_stats": PlayerSeasonStats,
    "team_season_stats": TeamSeasonStats,
    "lineups": Lineups,
    "rosters": Rosters,
    "coaches": Coaches,
    "schedules": Schedules,
    "player_game_logs": PlayerGameLogs,
    "pbp": Pbp,
    "game_rosters": GameRosters,
    "officials": Officials,
    "player_boxscores": PlayerBoxscores,
    "team_boxscores": TeamBoxscores,
    "shots": Shots,
    "schedule_master": ScheduleMaster,
    "games_in_data_repo": GamesInDataRepo,
}


def polars_schema(dataset: str) -> pl.Schema:
    """The dataset's declared columns and dtypes as a polars Schema."""
    model = MODELS[dataset]
    fields: dict[str, pl.DataType] = {}
    for name, info in model.model_fields.items():
        annotation = info.annotation
        args = getattr(annotation, "__args__", None)
        base = next((a for a in args if a is not type(None)), str) if args else annotation
        fields[name] = _PL_TYPES.get(base, pl.Utf8)
    return pl.Schema(fields)


#: Dtypes losslessly readable as the declared wider type.
_WIDENABLE_INT = {pl.Int8, pl.Int16, pl.Int32, pl.UInt8, pl.UInt16, pl.UInt32}


def check_frame(dataset: str, frame: pl.DataFrame) -> list[str]:
    """Frame-level schema check. Returns problems; empty means it matches.

    Widening is tolerated (an Int32 id read back from an older asset is
    losslessly an Int64, a Float32 a Float64); narrowing and type changes are
    not.
    """
    declared = polars_schema(dataset)
    problems: list[str] = []
    for name, dtype in declared.items():
        if name not in frame.columns:
            problems.append(f"{dataset}: missing column {name!r}")
            continue
        actual = frame.schema[name]
        if actual == dtype:
            continue
        if dtype == pl.Int64 and actual in _WIDENABLE_INT:
            continue
        if dtype == pl.Float64 and actual == pl.Float32:
            continue
        if actual == pl.Null:
            # An all-null column matches any declared dtype.
            continue
        problems.append(f"{dataset}: {name!r} is {actual}, declared {dtype}")
    return problems


def check_stem(stem: str, frame: pl.DataFrame) -> list[str]:
    """Resolve the dataset behind a release write stem and check the frame.

    Write stems carry the season suffix (``standings_2025``); the registry stem
    is the prefix. A stem no model covers (e.g. ``draft``, which has never
    published an asset to derive a schema from) returns no problems.
    """
    from nba_data_build.reshape.datasets import DATASETS

    for spec in DATASETS:
        if stem == spec.stem or stem.startswith(f"{spec.stem}_"):
            if spec.key in MODELS:
                return check_frame(spec.key, frame)
            return []
    return []
