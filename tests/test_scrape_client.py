from nba_data_build.scrape.client import V3Client
from nba_data_build.scrape.proxy import RoundRobin, load_proxies, redact


def test_roundrobin_cycles_and_builds_url():
    rr = RoundRobin([{"ip": "1.2.3.4", "port": "8000", "login": "u", "password": "p"}])
    url = rr.next()
    assert url == "http://u:p@1.2.3.4:8000"


def test_roundrobin_cycles_through_multiple_proxies():
    proxies = [
        {"ip": "1.1.1.1", "port": "1", "login": "u", "password": "p"},
        {"ip": "2.2.2.2", "port": "2", "login": "u", "password": "p"},
    ]
    rr = RoundRobin(proxies)
    seen = {rr.next() for _ in range(4)}
    assert seen == {"http://u:p@1.1.1.1:1", "http://u:p@2.2.2.2:2"}


def test_roundrobin_empty_pool_returns_none():
    rr = RoundRobin([])
    assert rr.next() is None


def test_redact_hides_credentials():
    assert redact("http://u:p@1.2.3.4:8000") == "http://1.2.3.4:8000"


def test_redact_noop_without_credentials():
    assert redact("http://1.2.3.4:8000") == "http://1.2.3.4:8000"


def test_load_proxies_empty_when_env_unset(monkeypatch):
    monkeypatch.delenv("PROXY_ENDPOINT", raising=False)
    monkeypatch.delenv("PROXY_KEY", raising=False)
    monkeypatch.delenv("PROXY_PKG", raising=False)
    assert load_proxies() == []


def test_load_proxies_never_raises_on_unreachable_endpoint(monkeypatch):
    monkeypatch.setenv("PROXY_ENDPOINT", "http://127.0.0.1:1")  # nothing listening
    monkeypatch.setenv("PROXY_KEY", "fake")
    monkeypatch.setenv("PROXY_PKG", "fake")
    assert load_proxies() == []


def test_client_uses_injected_transport_no_network():
    calls = []

    def fake(kind, game_id, **params):
        calls.append((kind, game_id, params))
        return {"kind": kind}

    c = V3Client(transport=fake)
    assert c.fetch_pbp("0022300001") == {"kind": "pbp"}
    assert c.fetch_box("0022300001") == {"kind": "box"}
    periods = c.fetch_box_periods("0022300001", 4)
    assert set(periods) == {1, 2, 3, 4}
    assert [k for k, _, _ in calls][:2] == ["pbp", "box"]


def test_client_fetch_box_periods_calls_bucket_and_proxy_per_period():
    calls = []

    def fake(kind, game_id, **params):
        calls.append(params)
        return {}

    class FakeBucket:
        def __init__(self):
            self.n = 0

        def acquire(self):
            self.n += 1

    class FakeProxies:
        def __init__(self):
            self.n = 0

        def next(self):
            self.n += 1
            return f"http://proxy{self.n}"

    bucket = FakeBucket()
    proxies = FakeProxies()
    c = V3Client(transport=fake, proxies=proxies, bucket=bucket)
    c.fetch_box_periods("0022300001", 3)
    assert bucket.n == 3
    assert proxies.n == 3
    assert [p["proxy_url"] for p in calls] == ["http://proxy1", "http://proxy2", "http://proxy3"]
