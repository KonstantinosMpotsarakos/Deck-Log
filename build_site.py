"""
build_site.py

Reads articles out of data/articles.db and renders the static site into
/docs (GitHub Pages serves straight from that folder on the default
branch, no separate hosting needed).

Usage:
    python build_site.py
"""

import os
import shutil
import sqlite3
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "articles.db")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
OUTPUT_DIR = os.path.join(BASE_DIR, "docs")

MAX_PER_COLUMN = 60


def fetch_articles(conn, category, limit):
    rows = conn.execute(
        """
        SELECT title, link, source, published, summary_en, summary_el
        FROM articles
        WHERE category = ?
        ORDER BY published DESC
        LIMIT ?
        """,
        (category, limit),
    ).fetchall()
    articles = []
    for i, (title, link, source, published, summary_en, summary_el) in enumerate(rows):
        try:
            dt = datetime.fromisoformat(published)
            date_str = dt.strftime("%d %b %Y")
        except ValueError:
            date_str = ""
        articles.append(
            {
                "entry_no": str(len(rows) - i).zfill(4),
                "title": title,
                "link": link,
                "source": source,
                "date": date_str,
                "summary_en": summary_en,
                "summary_el": summary_el,
            }
        )
    return articles


def main():
    if not os.path.exists(DB_PATH):
        print("No database found yet. Run fetch_and_digest.py first.")
        return

    conn = sqlite3.connect(DB_PATH)
    greek_articles = fetch_articles(conn, "greek", MAX_PER_COLUMN)
    intl_articles = fetch_articles(conn, "international", MAX_PER_COLUMN)
    conn.close()

    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("index.html")

    html = template.render(
        greek_articles=greek_articles,
        intl_articles=intl_articles,
        generated_at=datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
        total_count=len(greek_articles) + len(intl_articles),
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    static_out = os.path.join(OUTPUT_DIR, "static")
    if os.path.exists(static_out):
        shutil.rmtree(static_out)
    shutil.copytree(STATIC_DIR, static_out)

    # .nojekyll so GitHub Pages doesn't try to run Jekyll over the /docs folder
    open(os.path.join(OUTPUT_DIR, ".nojekyll"), "w").close()

    print(f"Built site: {len(greek_articles)} Greek entries, {len(intl_articles)} international entries.")
    print(f"Output written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
