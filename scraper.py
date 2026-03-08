"""Web scraper that detects page changes and sends CallMeBot notifications."""

import hashlib
import logging
import os
import sys
import urllib.parse

import requests
from bs4 import BeautifulSoup

SNAPSHOT_FILE = "snapshot.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def get_env(name: str) -> str:
    """Return the value of a required environment variable or exit with an error."""
    value = os.environ.get(name)
    if not value:
        logger.error("Required environment variable '%s' is not set.", name)
        sys.exit(1)
    return value


def fetch_page(url: str) -> str:
    """Fetch the HTML content of *url* and return its text."""
    logger.info("Fetching URL: %s", url)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def extract_text(html: str) -> str:
    """Parse *html* and return normalised visible text for hashing."""
    soup = BeautifulSoup(html, "lxml")
    # Remove script / style noise so that only meaningful content is hashed
    for tag in soup(["script", "style", "meta", "link"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def compute_hash(content: str) -> str:
    """Return the SHA-256 hex digest of *content*."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_snapshot() -> str | None:
    """Return the previously stored hash, or *None* if no snapshot exists."""
    if not os.path.exists(SNAPSHOT_FILE):
        return None
    with open(SNAPSHOT_FILE, encoding="utf-8") as fh:
        return fh.read().strip() or None


def save_snapshot(hash_value: str) -> None:
    """Persist *hash_value* to the snapshot file."""
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as fh:
        fh.write(hash_value + "\n")
    logger.info("Snapshot saved to '%s'.", SNAPSHOT_FILE)


def send_notification(message: str) -> None:
    """Send *message* via the CallMeBot WhatsApp webhook."""
    phone = get_env("CALLMEBOT_PHONE")
    api_key = get_env("CALLMEBOT_APIKEY")

    encoded_message = urllib.parse.quote(message)
    url = (
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={phone}&text={encoded_message}&apikey={api_key}"
    )

    logger.info("Sending notification via CallMeBot...")
    response = requests.get(url, timeout=30)
    if response.ok:
        logger.info("Notification sent successfully.")
    else:
        logger.warning(
            "Notification request returned status %s: %s",
            response.status_code,
            response.text,
        )


def main() -> None:
    """Entry point: scrape → compare → notify if changed."""
    scrape_url = get_env("SCRAPE_URL")

    html = fetch_page(scrape_url)
    text = extract_text(html)
    current_hash = compute_hash(text)
    logger.info("Current page hash: %s", current_hash)

    previous_hash = load_snapshot()

    if previous_hash is None:
        logger.info("No previous snapshot found. Saving initial state.")
        save_snapshot(current_hash)
        return

    if current_hash == previous_hash:
        logger.info("No changes detected. Exiting.")
        return

    logger.info(
        "Change detected! Previous hash: %s — Current hash: %s",
        previous_hash,
        current_hash,
    )
    save_snapshot(current_hash)
    send_notification(
        f"🔔 Change detected on {scrape_url}\n"
        f"Previous: {previous_hash[:12]}…\n"
        f"Current:  {current_hash[:12]}…"
    )


if __name__ == "__main__":
    main()
