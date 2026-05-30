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

get_proxy_ips <- function(
    api_key = Sys.getenv("PROXY_KEY"),
    user_package = Sys.getenv("PROXY_PKG"),
    proxy_endpoint = Sys.getenv("PROXY_ENDPOINT")) {
  res <- httr::RETRY(
    "GET",
    glue::glue("{proxy_endpoint}/{user_package}.json"),
    httr::add_headers(Authorization = paste(api_key))) %>%
    httr::content(as = "text", encoding = "UTF-8")

  resp <- res %>%
    jsonlite::fromJSON() %>%
    purrr::pluck("data")

  login <- resp$login
  password <- resp$password
  ips <- resp$ippacks

  ips$login <- login
  ips$password <- password
  proxies <- ips %>%
    dplyr::select("ip", "port_http", "login", "password")
  return(proxies)
}

select_proxy <- function(proxies = get_proxy_ips()) {
  proxy <- sample(proxies$ip, 1)          # pick a random proxy from the list above
  proxy_selected <- proxies %>%
    dplyr::filter(.data$ip == proxy)
  my_proxy <- httr::use_proxy(url = proxy_selected$ip,
                              port = proxy_selected$port,
                              username = proxy_selected$login,
                              password = proxy_selected$password)
  return(my_proxy)
}


# ----------------------------------------------------------------------------
# Rate limiter + round-robin proxy rotation for the NBA Stats endpoints.
#
# stats.nba.com shares a request budget (empirically ~200-300 requests of any
# type per ~10 minutes). Each nba_pbp() call hits several endpoints, so budget
# at the request level and treat one game as `n_hits` requests. Trailing-window
# token bucket: drop timestamps older than the window, sleep until a request
# fits, then record it. Env-tunable so the cap can be adjusted once the true
# limit is known.
#
# NOTE: do NOT wrap the pbp fetch in furrr/future_map -- parallel workers fire
# simultaneous requests that blow the shared budget, and this limiter state
# lives in the main process only. Keep the fetch loop sequential.
# ----------------------------------------------------------------------------
.rate_state <- new.env(parent = emptyenv())
.rate_state$ts <- numeric(0)

rate_limit <- function(n_hits   = as.integer(Sys.getenv("STATS_RATE_HITS", "3")),
                       max_calls = as.integer(Sys.getenv("STATS_RATE_MAX", "250")),
                       window_s  = as.numeric(Sys.getenv("STATS_RATE_WINDOW", "600"))) {
  n_hits <- max(1L, as.integer(n_hits))
  now <- as.numeric(Sys.time())
  .rate_state$ts <- .rate_state$ts[.rate_state$ts > now - window_s]
  while (length(.rate_state$ts) + n_hits > max_calls && length(.rate_state$ts) > 0) {
    wait <- (.rate_state$ts[1] + window_s) - now + 0.05
    Sys.sleep(max(0.05, wait))
    now <- as.numeric(Sys.time())
    .rate_state$ts <- .rate_state$ts[.rate_state$ts > now - window_s]
  }
  .rate_state$ts <- c(.rate_state$ts, rep(now, n_hits))
  invisible(length(.rate_state$ts))
}

# Round-robin proxy selection with a random starting permutation ("rotating
# proxies initialized at random") -- spreads load evenly across IPs instead of
# the sampling-with-replacement select_proxy() does. Same httr::use_proxy()
# return shape as select_proxy() so it is a drop-in replacement.
.proxy_rr <- new.env(parent = emptyenv())
.proxy_rr$order <- NULL
.proxy_rr$pos <- 0L

next_proxy <- function(proxies = get_proxy_ips()) {
  if (is.null(proxies) || nrow(proxies) == 0) return(NULL)
  if (is.null(.proxy_rr$order) || length(.proxy_rr$order) != nrow(proxies)) {
    .proxy_rr$order <- sample(seq_len(nrow(proxies)))   # random initialisation
    .proxy_rr$pos <- 0L
  }
  .proxy_rr$pos <- (.proxy_rr$pos %% length(.proxy_rr$order)) + 1L
  ps <- proxies[.proxy_rr$order[.proxy_rr$pos], , drop = FALSE]
  httr::use_proxy(url = ps$ip, port = ps$port,
                  username = ps$login, password = ps$password)
}
