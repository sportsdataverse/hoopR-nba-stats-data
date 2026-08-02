import time

from nba_data_build.scrape.rate_limit import TokenBucket


def test_bucket_allows_up_to_cap_without_sleeping():
    b = TokenBucket(n_hits=1, max_calls=5, window_s=100.0)
    t0 = time.monotonic()
    for _ in range(5):
        b.acquire()
    assert time.monotonic() - t0 < 0.2  # 5 fit in the window, no sleep


def test_bucket_sleeps_when_window_full(monkeypatch):
    slept = []
    monkeypatch.setattr("nba_data_build.scrape.rate_limit.time.sleep", lambda s: slept.append(s))
    b = TokenBucket(n_hits=1, max_calls=2, window_s=100.0)
    for _ in range(3):
        b.acquire()
    assert slept and slept[0] > 0  # the 3rd acquire had to wait


def test_bucket_env_defaults(monkeypatch):
    monkeypatch.setenv("STATS_RATE_HITS", "5")
    monkeypatch.setenv("STATS_RATE_MAX", "42")
    monkeypatch.setenv("STATS_RATE_WINDOW", "60")
    b = TokenBucket()
    assert b.n_hits == 5
    assert b.max_calls == 42
    assert b.window_s == 60.0


def test_bucket_n_hits_floored_at_one():
    b = TokenBucket(n_hits=0, max_calls=5, window_s=100.0)
    assert b.n_hits == 1
