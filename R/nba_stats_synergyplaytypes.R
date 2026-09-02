#' Methodological twin of `python/nba_data_build/synergy_cli.py`.
#'
#' Standing policy (2026-08-03): this repo carries BOTH pipelines — Python is
#' primary and gets the work, R is maintained alongside as the language twin so
#' the METHOD survives in two places. Adding the synergy dataset on the Python
#' side therefore moves the R side with it.
#'
#' Two deliberate differences from the Python producer:
#'
#'   1. Python reads the committed raw store in `hoopR-nba-stats-raw` and makes
#'      no network calls; this twin calls `hoopR::nba_synergyplaytypes()`
#'      directly, because the R chain has no raw-store reader. Same cube, same
#'      variant grid, different source of bytes.
#'   2. There is **no `sportsdataverse_save()` here, on purpose.** The R stages
#'      in this repo publish to the LIVE release with no dry-run gate, so this
#'      twin only writes locally. Publishing is the Python path's job:
#'      `python -m nba_data_build.synergy_cli --seasons <y> --publish`.
#'
#' The empty-variant skip below is the same guard the Python builder enforces:
#' pre-2015 seasons and the in-progress season return a well-formed response
#' with zero rows, and writing those produces schema-only files that make a tag
#' advertise coverage it does not have.

# Declare exactly what this file calls -- hoopR, readr, tibble -- so a missing
# package fails here with a clear message instead of deep inside the season loop.
# (dplyr was in the original header and is NOT used; carrying it would have been
# a dependency the file does not have.)
for (pkg in c("hoopR", "readr", "tibble")) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    stop(sprintf("nba_stats_synergyplaytypes.R needs the %s package", pkg), call. = FALSE)
  }
}

# 88 variants = season_type x play_type x type_grouping x per_mode.
play_types <- c(
  "Isolation", "Transition", "PRBallHandler", "PRRollman", "Postup",
  "Spotup", "Handoff", "Cut", "OffScreen", "OffRebound", "Misc"
)
season_types <- c("Regular Season", "Playoffs")
groupings <- c("Offensive", "Defensive")
per_modes <- c("PerGame", "Totals")

#' Compile one season of the synergy cube to `out_dir`.
#'
#' Returns a tibble of what was written. A variant with zero rows is skipped and
#' reported, never written.
synergy_season <- function(season_year, out_dir = "nba/synergy") {
  dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
  season <- hoopR::year_to_season(season_year - 1)
  written <- list()

  for (st in season_types) {
    for (pt in play_types) {
      for (tg in groupings) {
        for (pm in per_modes) {
          res <- try(
            hoopR::nba_synergyplaytypes(
              season = season, season_type = st, play_type = pt,
              type_grouping = tg, per_mode = pm
            )$SynergyPlayType,
            silent = TRUE
          )
          if (inherits(res, "try-error") || is.null(res) || nrow(res) == 0) {
            message(sprintf("synergy_empty %s %s %s %s %s", season, st, pt, tg, pm))
            next
          }
          # The response carries PLAY_TYPE/TYPE_GROUPING; the filename below is
          # built from the REQUESTED pt/tg. Writing without comparing them files a
          # mislabelled response under the wrong variant, and the two disagreeing
          # is the only signal it happened -- the same guard the Python builder's
          # `_stamp` applies, with the same separator-insensitive normalisation so
          # "PRRollMan" matches "PRRollman".
          norm <- function(x) gsub("[^a-z0-9]", "", tolower(as.character(x)))
          for (chk in list(
            list(col = "PLAY_TYPE", want = pt),
            list(col = "TYPE_GROUPING", want = tg)
          )) {
            if (!chk$col %in% names(res)) next
            got <- unique(norm(res[[chk$col]]))
            got <- got[!is.na(got) & nzchar(got)]
            if (length(got) && !identical(got, norm(chk$want))) {
              stop(sprintf(
                "%s %s %s %s %s: request says %s=%s but payload says %s -- capture is mislabelled",
                season, st, pt, tg, pm, chk$col, chk$want, paste(sort(got), collapse = ",")
              ), call. = FALSE)
            }
          }
          stem <- sprintf(
            "%s_%s_%s_%s",
            ifelse(st == "Regular Season", "regular-season", "playoffs"),
            tolower(pt), tolower(tg), tolower(pm)
          )
          res$season <- season_year
          res$season_type <- ifelse(st == "Regular Season", "regular-season", "playoffs")
          res$per_mode <- tolower(pm)
          path <- file.path(out_dir, sprintf("%s_%s.csv", stem, season_year))
          readr::write_csv(res, path)
          written[[stem]] <- nrow(res)
        }
      }
    }
  }
  tibble::tibble(variant = names(written), rows = unlist(written))
}

# Seasons with rows, measured 2026-09-02: 1996-2005 and the in-progress season
# return zero rows. This function takes ONE season and has no default range --
# the Python producer owns the 2015-2025 default; call this per season.
# synergy_season(2024)
