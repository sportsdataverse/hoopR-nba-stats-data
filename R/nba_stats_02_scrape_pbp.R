rm(list = ls())
gcol <- gc()
# lib_path <- Sys.getenv("R_LIBS")
# if (!requireNamespace("pacman", quietly = TRUE)) {
#   install.packages("pacman", lib = Sys.getenv("R_LIBS"), repos = "http://cran.us.r-project.org")
# }
suppressPackageStartupMessages(suppressMessages(library(dplyr)))
suppressPackageStartupMessages(suppressMessages(library(magrittr)))
suppressPackageStartupMessages(suppressMessages(library(jsonlite)))
suppressPackageStartupMessages(suppressMessages(library(purrr)))
suppressPackageStartupMessages(suppressMessages(library(progressr)))
suppressPackageStartupMessages(suppressMessages(library(data.table)))
suppressPackageStartupMessages(suppressMessages(library(arrow)))
suppressPackageStartupMessages(suppressMessages(library(glue)))
suppressPackageStartupMessages(suppressMessages(library(optparse)))

source("R/utils.R")


option_list <- list(
  make_option(c("-s", "--start_year"),
              action = "store",
              default = hoopR:::most_recent_nba_season(),
              type = "integer",
              help = "Start year of the seasons to process"),
  make_option(c("-e", "--end_year"),
              action = "store",
              default = hoopR:::most_recent_nba_season(),
              type = "integer",
              help = "End year of the seasons to process"),
  make_option(c("-r", "--rescrape"),
              action = "store",
              default = FALSE,
              type = "logical",
              help = "Rescrape the raw JSON files from web api")
)
opt <- parse_args(OptionParser(option_list = option_list))
options(list(stringsAsFactors = FALSE, scipen = 999))

years_vec <- (opt$s - 1):(opt$e - 1)
rescrape <- opt$r

proxies_df <- get_proxy_ips()

seasons_vec <- purrr::map(years_vec, function(x) {
  hoopR::year_to_season(x)
  }) %>%
  unlist()

nba_stats_pbp_season <- function(season) {
  # END-year file labels (1996-97 -> 1997), the ecosystem convention since 2026-09-30.
  # The tree carries parquet only; the release still gets all three formats.
  season_end <- as.integer(substr(season, 1, 4)) + 1L

  schedules_df <- readRDS(paste0("nba_stats/schedules/rds/schedule_", season, ".rds"))

  ifelse(!dir.exists(file.path("nba_stats/json")), dir.create("nba_stats/json"), FALSE)
  ifelse(!dir.exists(file.path("nba_stats/json/pbp")), dir.create("nba_stats/json/pbp"), FALSE)
  pbp_list <- list.files(path = "nba_stats/json/pbp")

  if (length(pbp_list) > 0) {
    pbp_list <- as.integer(stringr::str_extract(pbp_list, "\\d+"))
    pbp_list <- gsub(".json", "", pbp_list)
    pbp_game_ids <- lapply(pbp_list, function(x) {
      hoopR:::pad_id(x)
    })
  }

  season_pbp_list <- schedules_df %>%
    dplyr::filter(.data$game_id %in% pbp_game_ids) %>%
    dplyr::pull("game_id")

  if (rescrape == FALSE) {
    schedules_year <- schedules_df %>%
      dplyr::filter(.data$season == season,
                    .data$home_team_id != 0,
                    .data$game_status == 3,
                    !(.data$game_id %in% pbp_game_ids))
  } else {
    schedules_year <- schedules_df %>%
      dplyr::filter(.data$season == season,
                    .data$home_team_id != 0,
                    .data$game_status == 3)
  }


  ## --- Scraping the PBP -----
  games_to_scrape_list <- unique(schedules_year$game_id)

  if (length(games_to_scrape_list) > 0) {

    cli::cli_progress_step(msg = "Downloading {season} NBA Stats pbps ({length(games_to_scrape_list)} games)",
                           msg_done = "Downloaded {season} NBA Stats pbps!")

    # Sequential ONLY -- never furrr/future_map. stats.nba.com shares a request
    # budget (~200-300 reqs/10min of any type) and each nba_pbp() call hits
    # several endpoints; parallel workers fire simultaneous requests that blow
    # that budget. rate_limit() (R/utils.R) throttles to the shared budget
    # before each game (one game = several hits); next_proxy() rotates IPs
    # round-robin over a randomly-shuffled pool.
    nba_stats_df <- purrr::map_dfr(seq_along(games_to_scrape_list), function(x) {

      rate_limit()
      df <- hoopR::nba_pbp(game_id = hoopR:::pad_id(games_to_scrape_list[x]),
                           proxy = next_proxy(proxies = proxies_df)) # nolint
      df <-  df %>%
        dplyr::mutate(season = season)
      jsonlite::write_json(df, path = paste0("nba_stats/json/pbp/", hoopR:::pad_id(games_to_scrape_list[x]), ".json"))

      return(df)
    })

  } else {

    print(glue::glue("Skipping {season} season scrape, {length(games_to_scrape_list)} completed games left to scrape"))

  }


  ## --- Compiling the PBP ----
  pbp_list <- list.files(path = "nba_stats/json/pbp")

  if (length(pbp_list) > 0) {
    pbp_list <- as.integer(stringr::str_extract(pbp_list, "\\d+"))
    pbp_list <- gsub(".json", "", pbp_list)
    pbp_game_ids <- lapply(pbp_list, function(x) {
      hoopR:::pad_id(x)
    })
  }

  season_pbp_list <- schedules_df %>%
    dplyr::filter(.data$game_id %in% pbp_game_ids) %>%
    dplyr::pull("game_id")

  cli::cli_progress_step(msg = "Compiling {season} NBA Stats pbps ({length(season_pbp_list)} games)",
                         msg_done = "Compiled {season} NBA Stats pbps!")

  nba_stats_df <- purrr::map_dfr(season_pbp_list, function(x) {
    pbp <- glue::glue("nba_stats/json/pbp/{hoopR:::pad_id(x)}.json") %>%
      jsonlite::fromJSON()
    return(pbp)
  })

  nba_stats_df <- nba_stats_df %>%
    dplyr::left_join(schedules_df, by = c("game_id" = "game_id")) %>%
    dplyr::arrange(dplyr::desc(.data$game_date_est))


  ## --- Writing v2 PBP to the tree archive (no release: no tag carries v2) -----
  if (nrow(nba_stats_df) > 1) {
    nba_stats_df <- nba_stats_df %>%
      hoopR:::make_hoopR_data("NBA Stats Play-by-Play from hoopR data repository", Sys.time())

    dir.create("archive/nba_stats_pbp_v2", recursive = TRUE, showWarnings = FALSE)
    arrow::write_parquet(nba_stats_df, paste0("archive/nba_stats_pbp_v2/play_by_play_v2_", season_end, ".parquet"))
  }
  # The PBP-flagged per-season schedule_{E} tree files and the R master are
  # retired (2026-09-30): Python stage 99 builds the schedule master from raw
  # scheduleleaguev2 with in_* flags from the committed tree.
}

cli::cli_progress_step(msg = "Downloading {opt$s - 1}-{substr(opt$s,3,4)} to {opt$e -1}-{substr(opt$e,3,4)} seasons of NBA Stats play-by-play data",
                       msg_done = "Downloaded {opt$s - 1}-{substr(opt$s,3,4)} to {opt$e -1}-{substr(opt$e,3,4)} seasons of NBA Stats play-by-play data")

all_games <- purrr::map(seasons_vec, function(y) {
  nba_stats_pbp_season(y)
})


cli::cli_progress_message("")

rm(all_games)