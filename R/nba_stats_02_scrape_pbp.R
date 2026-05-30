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

    future::plan("multisession")
    nba_stats_df <- furrr::future_map_dfr(seq_along(games_to_scrape_list), function(x) {

      df <- hoopR::nba_pbp(game_id = hoopR:::pad_id(games_to_scrape_list[x]),
                           proxy = select_proxy(proxies = proxies_df)) # nolint
      df <-  df %>%
        dplyr::mutate(season = season)
      jsonlite::write_json(df, path = paste0("nba_stats/json/pbp/", hoopR:::pad_id(games_to_scrape_list[x]), ".json"))
      Sys.sleep(1)

      return(df)
    }, .options = furrr::furrr_options(seed = TRUE))

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


  ## --- Writing PBP to disk and pushing to nba_stats_pbp release -----
  if (nrow(nba_stats_df) > 1) {
    nba_stats_df <- nba_stats_df %>%
      hoopR:::make_hoopR_data("NBA Stats Play-by-Play from hoopR data repository", Sys.time())

    ifelse(!dir.exists(file.path("nba_stats/pbp")), dir.create(file.path("nba_stats/pbp")), FALSE)
    ifelse(!dir.exists(file.path("nba_stats/pbp/csv")), dir.create(file.path("nba_stats/pbp/csv")), FALSE)
    data.table::fwrite(nba_stats_df, file = paste0("nba_stats/pbp/csv/play_by_play_", season, ".csv.gz"))

    ifelse(!dir.exists(file.path("nba_stats/pbp/rds")), dir.create(file.path("nba_stats/pbp/rds")), FALSE)
    saveRDS(nba_stats_df, glue::glue("nba_stats/pbp/rds/play_by_play_{season}.rds"))

    ifelse(!dir.exists(file.path("nba_stats/pbp/parquet")), dir.create(file.path("nba_stats/pbp/parquet")), FALSE)
    arrow::write_parquet(nba_stats_df, paste0("nba_stats/pbp/parquet/play_by_play_", season, ".parquet"))

    sportsdataversedata::sportsdataverse_save(
      data_frame = nba_stats_df,
      file_name =  glue::glue("play_by_play_{season}"),
      sportsdataverse_type = "play-by-play data",
      release_tag = "nba_stats_pbp",
      file_types = c("rds", "csv", "parquet"),
      .token = Sys.getenv("GITHUB_PAT")
    )
  }

  ## --- Adding PBP Flag to Schedules -----
  if (nrow(nba_stats_df) > 0) {
    schedules_df <- schedules_df %>%
      dplyr::mutate(
        PBP = ifelse(.data$game_id %in% unique(nba_stats_df$game_id), TRUE, FALSE)
      )
  } else {
    schedules_df$PBP <- FALSE
  }
  schedules_df <- schedules_df %>%
    dplyr::arrange(dplyr::desc(.data$game_date_est)) %>%
    hoopR:::make_hoopR_data("NBA Stats Schedule from hoopR data repository", Sys.time())

  ## --- Writing Schedules to disk -----
  if (nrow(nba_stats_df) > 0) {
    ifelse(!dir.exists(file.path("nba_stats/schedules")), dir.create(file.path("nba_stats/schedules")), FALSE)

    ifelse(!dir.exists(file.path("nba_stats/schedules/csv")), dir.create(file.path("nba_stats/schedules/csv")), FALSE)
    data.table::fwrite(schedules_df, paste0("nba_stats/schedules/csv/schedule_", season, ".csv"))

    ifelse(!dir.exists(file.path("nba_stats/schedules/rds")), dir.create(file.path("nba_stats/schedules/rds")), FALSE)
    saveRDS(schedules_df, paste0("nba_stats/schedules/rds/schedule_", season, ".rds"))

    ifelse(!dir.exists(file.path("nba_stats/schedules/parquet")),
           dir.create(file.path("nba_stats/schedules/parquet")), FALSE)
    arrow::write_parquet(schedules_df, paste0("nba_stats/schedules/parquet/schedule_", season, ".parquet"))
  }
}

cli::cli_progress_step(msg = "Downloading {opt$s - 1}-{substr(opt$s,3,4)} to {opt$e -1}-{substr(opt$e,3,4)} seasons of NBA Stats play-by-play data",
                       msg_done = "Downloaded {opt$s - 1}-{substr(opt$s,3,4)} to {opt$e -1}-{substr(opt$e,3,4)} seasons of NBA Stats play-by-play data")

all_games <- purrr::map(seasons_vec, function(y) {
  nba_stats_pbp_season(y)
})



## --- Compiling Schedules and writing master to disk -----
cli::cli_progress_step(msg = "Compiling NBA Stats master schedule",
                       msg_done = "NBA Stats master schedule compiled and written to disk")

sched_list <- list.files(path = glue::glue("nba_stats/schedules/rds"))
master_schedules_df <- purrr::map_dfr(sched_list, function(x) {
  sched <- readRDS(paste0("nba_stats/schedules/rds/", x))
  return(sched)
})

master_schedules_df <- master_schedules_df %>%
  dplyr::arrange(dplyr::desc(.data$game_date_est)) %>%
  hoopR:::make_hoopR_data("NBA Stats Schedule from hoopR data repository", Sys.time())

data.table::fwrite(master_schedules_df, "nba_stats/nba_stats_schedule_master.csv")
saveRDS(master_schedules_df, "nba_stats/nba_stats_schedule_master.rds")
arrow::write_parquet(master_schedules_df, "nba_stats/nba_stats_schedule_master.parquet")

cli::cli_progress_message("")

rm(all_games)
rm(master_schedules_df)