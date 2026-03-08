"""Tests for scraper.py."""

import importlib
import sys
from unittest.mock import MagicMock, mock_open, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_scraper():
    """Import (or re-import) the scraper module so patching takes effect."""
    if "scraper" in sys.modules:
        del sys.modules["scraper"]
    return importlib.import_module("scraper")


# ---------------------------------------------------------------------------
# get_env
# ---------------------------------------------------------------------------

def test_get_env_present(monkeypatch):
    scraper = _reload_scraper()
    monkeypatch.setenv("MY_VAR", "hello")
    assert scraper.get_env("MY_VAR") == "hello"


def test_get_env_missing_exits(monkeypatch):
    scraper = _reload_scraper()
    monkeypatch.delenv("MY_VAR", raising=False)
    import pytest
    with pytest.raises(SystemExit):
        scraper.get_env("MY_VAR")


# ---------------------------------------------------------------------------
# compute_hash
# ---------------------------------------------------------------------------

def test_compute_hash_deterministic():
    scraper = _reload_scraper()
    h1 = scraper.compute_hash("hello world")
    h2 = scraper.compute_hash("hello world")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest length


def test_compute_hash_different_for_different_content():
    scraper = _reload_scraper()
    assert scraper.compute_hash("foo") != scraper.compute_hash("bar")


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------

def test_extract_text_removes_scripts():
    scraper = _reload_scraper()
    html = "<html><body><script>alert(1)</script><p>Hello</p></body></html>"
    text = scraper.extract_text(html)
    assert "alert" not in text
    assert "Hello" in text


def test_extract_text_removes_styles():
    scraper = _reload_scraper()
    html = "<html><body><style>body{color:red}</style><p>World</p></body></html>"
    text = scraper.extract_text(html)
    assert "color" not in text
    assert "World" in text


# ---------------------------------------------------------------------------
# load_snapshot / save_snapshot
# ---------------------------------------------------------------------------

def test_load_snapshot_returns_none_when_missing(tmp_path, monkeypatch):
    scraper = _reload_scraper()
    monkeypatch.setattr(scraper, "SNAPSHOT_FILE", str(tmp_path / "snapshot.txt"))
    assert scraper.load_snapshot() is None


def test_load_snapshot_returns_stored_hash(tmp_path, monkeypatch):
    scraper = _reload_scraper()
    snapshot = tmp_path / "snapshot.txt"
    snapshot.write_text("abc123\n")
    monkeypatch.setattr(scraper, "SNAPSHOT_FILE", str(snapshot))
    assert scraper.load_snapshot() == "abc123"


def test_save_snapshot_writes_hash(tmp_path, monkeypatch):
    scraper = _reload_scraper()
    snapshot = tmp_path / "snapshot.txt"
    monkeypatch.setattr(scraper, "SNAPSHOT_FILE", str(snapshot))
    scraper.save_snapshot("deadbeef")
    assert snapshot.read_text().strip() == "deadbeef"


# ---------------------------------------------------------------------------
# fetch_page
# ---------------------------------------------------------------------------

def test_fetch_page_returns_html(monkeypatch):
    scraper = _reload_scraper()
    mock_resp = MagicMock()
    mock_resp.text = "<html>ok</html>"
    mock_resp.raise_for_status = MagicMock()

    with patch("scraper.requests.get", return_value=mock_resp) as mock_get:
        result = scraper.fetch_page("https://example.com")

    mock_get.assert_called_once_with("https://example.com", timeout=30)
    assert result == "<html>ok</html>"


# ---------------------------------------------------------------------------
# send_notification
# ---------------------------------------------------------------------------

def test_send_notification_calls_correct_url(monkeypatch):
    scraper = _reload_scraper()
    monkeypatch.setenv("CALLMEBOT_PHONE", "5511999999999")
    monkeypatch.setenv("CALLMEBOT_APIKEY", "testkey")

    mock_resp = MagicMock()
    mock_resp.ok = True

    with patch("scraper.requests.get", return_value=mock_resp) as mock_get:
        scraper.send_notification("Hello World")

    call_url = mock_get.call_args[0][0]
    assert call_url.startswith("https://api.callmebot.com/whatsapp.php")
    assert "5511999999999" in call_url
    assert "testkey" in call_url
    assert "Hello" in call_url


# ---------------------------------------------------------------------------
# main — integration-level
# ---------------------------------------------------------------------------

def test_main_saves_initial_snapshot(tmp_path, monkeypatch):
    scraper = _reload_scraper()
    snapshot = tmp_path / "snapshot.txt"
    monkeypatch.setattr(scraper, "SNAPSHOT_FILE", str(snapshot))
    monkeypatch.setenv("SCRAPE_URL", "https://example.com")

    mock_resp = MagicMock()
    mock_resp.text = "<html><body><p>content</p></body></html>"
    mock_resp.raise_for_status = MagicMock()

    with patch("scraper.requests.get", return_value=mock_resp):
        scraper.main()

    assert snapshot.exists()
    assert len(snapshot.read_text().strip()) == 64


def test_main_no_notification_when_unchanged(tmp_path, monkeypatch):
    scraper = _reload_scraper()
    snapshot = tmp_path / "snapshot.txt"
    monkeypatch.setattr(scraper, "SNAPSHOT_FILE", str(snapshot))
    monkeypatch.setenv("SCRAPE_URL", "https://example.com")

    html = "<html><body><p>content</p></body></html>"
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    # First run — saves snapshot
    with patch("scraper.requests.get", return_value=mock_resp):
        scraper.main()

    notify_mock = MagicMock()
    monkeypatch.setattr(scraper, "send_notification", notify_mock)

    # Second run — same content, no notification
    with patch("scraper.requests.get", return_value=mock_resp):
        scraper.main()

    notify_mock.assert_not_called()


def test_main_sends_notification_on_change(tmp_path, monkeypatch):
    scraper = _reload_scraper()
    snapshot = tmp_path / "snapshot.txt"
    monkeypatch.setattr(scraper, "SNAPSHOT_FILE", str(snapshot))
    monkeypatch.setenv("SCRAPE_URL", "https://example.com")
    monkeypatch.setenv("CALLMEBOT_PHONE", "5511999999999")
    monkeypatch.setenv("CALLMEBOT_APIKEY", "testkey")

    old_html = "<html><body><p>old content</p></body></html>"
    new_html = "<html><body><p>new content — changed!</p></body></html>"

    old_resp = MagicMock()
    old_resp.text = old_html
    old_resp.raise_for_status = MagicMock()

    # First run — save initial snapshot
    with patch("scraper.requests.get", return_value=old_resp):
        scraper.main()

    new_resp = MagicMock()
    new_resp.text = new_html
    new_resp.raise_for_status = MagicMock()

    notify_mock = MagicMock()
    monkeypatch.setattr(scraper, "send_notification", notify_mock)

    # Second run — different content → notification expected
    with patch("scraper.requests.get", return_value=new_resp):
        scraper.main()

    notify_mock.assert_called_once()
    message = notify_mock.call_args[0][0]
    assert message.startswith("🔔 Change detected on https://example.com")
