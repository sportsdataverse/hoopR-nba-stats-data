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
options(stringsAsFactors = FALSE)
options(scipen = 999)
years_vec <- (opt$s - 1):(opt$e - 1)
rescrape <- opt$r

proxies_df <- get_proxy_ips()

seasons_vec <- purrr::map(years_vec, function(x) {
  hoopR::year_to_season(x)
  }) %>%
  unlist()


schedules_df <- purrr::map_dfr(seq_along(seasons_vec), function(x) {
  cli::cli_progress_step(msg = "Downloading {seasons_vec[[x]]} NBA Stats schedule",
                         msg_done = "Downloaded {seasons_vec[[x]]} NBA Stats schedule!")

  completed_sched <- hoopR::nba_schedule(season = seasons_vec[[x]], proxy = select_proxy(proxies = proxies_df)) %>%
    dplyr::mutate(
      season = seasons_vec[[x]])

  completed_sched <- completed_sched %>%
    hoopR:::make_hoopR_data("NBA Stats Schedule from hoopR data repository", Sys.time())

  # END-year label (1996-97 -> 1997) since 2026-09-30. Release upload only: the
  # per-season nba_stats/schedules/parquet/schedule_{E} tree family was retired
  # 2026-09-30 -- Python stage 99 builds the schedule master from raw
  # scheduleleaguev2 (python/nba_stats_99_schedule_master_creation.py).
  season_end <- as.integer(substr(seasons_vec[[x]], 1, 4)) + 1L

  sportsdataversedata::sportsdataverse_save(
    data_frame = completed_sched,
    file_name = glue::glue("schedule_{season_end}"),
    sportsdataverse_type = "schedule data",
    release_tag = "nba_stats_schedules",
    pkg_function = "hoopR::load_nba_schedule()",
    file_types = c("rds", "csv", "parquet"),
    .token = Sys.getenv("GITHUB_PAT")
  )

  return(completed_sched)
})


cli::cli_progress_message("")