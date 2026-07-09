"""
fetch_and_digest.py

Pulls new articles from the Greek and international RSS feeds listed in
feeds.json, filters out anything unrelated to naval architecture / marine
engineering / shipping, and uses Claude to generate a short English AND
short Greek summary for each new article. Everything is stored in a local
SQLite database (data/articles.db) so re-running this script never creates
duplicates.

Usage:
    python fetch_and_digest.py                 # normal run
    python fetch_and_digest.py --check-feeds    # just test that each feed URL responds
    python fetch_and_digest.py --limit 5        # cap how many new articles get AI-summarized (useful while testing, saves API cost)

Requires the ANTHROPIC_API_KEY environment variable to be set.
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

import feedparser
from anthropic import Anthropic
from dateutil import parser as dateparser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDS_PATH = os.path.join(BASE_DIR, "feeds.json")
DB_PATH = os.path.join(BASE_DIR, "data", "articles.db")

# Model used for summarizing/translating. Haiku is fast and cheap, which
# matters since this runs on a schedule against potentially dozens of
# articles per run.
MODEL = "claude-haiku-4-5-20251001"

# Lightweight relevance filter so a broad feed (e.g. a general shipping
# section) doesn't pull in off-topic stories. An article passes if any
# keyword appears in its title or summary (case-insensitive).
KEYWORDS = [
    "ship", "vessel", "naval", "navy", "maritime", "marine", "shipyard",
    "shipbuilding", "tanker", "lng", "lpg", "container", "bulk carrier",
    "port", "offshore", "hull", "propulsion", "drydock", "dry dock",
    "classification society", "imo", "seafarer", "crew", "cargo",
    "freight", "charter", "flag state", "naval architecture",
    "ναυτιλία", "πλοίο", "πλοία", "ναυπηγ", "ναυτικ", "λιμάν", "λιμέν",
    "εμπορικό ναυτικό", "φορτηγό πλοίο", "δεξαμεν", "ναύλωση",
]


def load_feeds():
    with open(FEEDS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    sources = []
    for category in ("greek", "international"):
        for feed in data.get(category, []):
            sources.append({**feed, "category": category})
    return sources


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            link TEXT NOT NULL,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            original_language TEXT,
            published TEXT,
            fetched_at TEXT NOT NULL,
            summary_en TEXT,
            summary_el TEXT,
            raw_snippet TEXT
        )
        """
    )
    conn.commit()
    return conn


def article_id(link: str) -> str:
    return hashlib.sha256(link.encode("utf-8")).hexdigest()[:24]


def is_relevant(title: str, snippet: str) -> bool:
    text = f"{title} {snippet}".lower()
    return any(kw in text for kw in KEYWORDS)


def parse_published(entry) -> str:
    for field in ("published", "updated", "pubDate"):
        value = entry.get(field)
        if value:
            try:
                return dateparser.parse(value).astimezone(timezone.utc).isoformat()
            except (ValueError, TypeError):
                continue
    return datetime.now(timezone.utc).isoformat()


def clean_snippet(entry) -> str:
    raw = entry.get("summary", "") or entry.get("description", "")
    # very light tag strip, good enough for feeding to the model
    import re
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1200]


def summarize_with_claude(client: Anthropic, title: str, snippet: str, source: str) -> dict:
    prompt = f"""You are producing a short bilingual digest entry for a naval architecture and marine engineering news site.

Source: {source}
Title: {title}
Original text snippet: {snippet}

Write two summaries of this article, 1-2 sentences each, in your own words (do not quote the snippet verbatim):
1. An English summary.
2. A Greek summary (in Greek, φυσική ελληνική γλώσσα).

Respond ONLY with JSON, no preamble, no markdown fences, in exactly this shape:
{{"summary_en": "...", "summary_el": "..."}}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    text = text.strip("`")
    if text.lower().startswith("json"):
        text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {"summary_en": snippet[:280], "summary_el": ""}
    return data


def check_feeds(sources):
    print("Checking feed URLs...\n")
    for feed in sources:
        parsed = feedparser.parse(feed["url"])
        status = "OK" if parsed.entries else "NO ENTRIES / FAILED"
        print(f"  [{status:20}] {feed['name']:35} {feed['url']}")
        if parsed.bozo and not parsed.entries:
            print(f"      -> error: {parsed.bozo_exception}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-feeds", action="store_true", help="Just validate feed URLs and exit")
    parser.add_argument("--limit", type=int, default=None, help="Max number of new articles to summarize this run")
    args = parser.parse_args()

    sources = load_feeds()

    if args.check_feeds:
        check_feeds(sources)
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    client = Anthropic(api_key=api_key)
    conn = init_db()

    new_count = 0
    skipped_irrelevant = 0

    for feed in sources:
        print(f"Fetching: {feed['name']} ({feed['url']})")
        parsed = feedparser.parse(feed["url"])
        if not parsed.entries:
            print(f"  no entries returned, skipping")
            continue

        for entry in parsed.entries:
            link = entry.get("link")
            title = entry.get("title", "").strip()
            if not link or not title:
                continue

            aid = article_id(link)
            existing = conn.execute("SELECT id FROM articles WHERE id = ?", (aid,)).fetchone()
            if existing:
                continue

            snippet = clean_snippet(entry)

            if not is_relevant(title, snippet):
                skipped_irrelevant += 1
                continue

            if args.limit is not None and new_count >= args.limit:
                break

            print(f"  + new: {title[:70]}")
            digest = summarize_with_claude(client, title, snippet, feed["name"])

            conn.execute(
                """
                INSERT INTO articles
                    (id, title, link, source, category, original_language,
                     published, fetched_at, summary_en, summary_el, raw_snippet)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    title,
                    link,
                    feed["name"],
                    feed["category"],
                    feed.get("language", "en"),
                    parse_published(entry),
                    datetime.now(timezone.utc).isoformat(),
                    digest.get("summary_en", ""),
                    digest.get("summary_el", ""),
                    snippet,
                ),
            )
            conn.commit()
            new_count += 1

    print(f"\nDone. {new_count} new articles added, {skipped_irrelevant} skipped as off-topic.")
    conn.close()


if __name__ == "__main__":
    main()
