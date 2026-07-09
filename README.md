# Deck Log — naval architecture & marine engineering digest

An automated news site that pulls RSS feeds from Greek and international
maritime/naval-architecture sources, uses Claude to write a short English
and Greek summary of each new article, and rebuilds a static site on a
schedule. Once set up, it runs itself — you just maintain it.

## How it works

1. **`fetch_and_digest.py`** pulls each RSS feed in `feeds.json`, skips
   anything already seen, filters out off-topic stories with a keyword
   check, and asks Claude to write a short bilingual summary for each new
   article. Everything lands in `data/articles.db` (SQLite).
2. **`build_site.py`** reads that database and renders `docs/index.html` —
   a two-column page (Greek sources / international sources), styled like
   a ship's log.
3. **`.github/workflows/update.yml`** runs both scripts every 6 hours on
   GitHub's infrastructure, commits the updated database and site, and
   pushes. GitHub Pages serves whatever is in `/docs` on your default
   branch — so the site updates itself with no server to maintain.

## One-time setup

1. **Create a GitHub repo** and push this folder to it (see commands
   below).
2. **Get an Anthropic API key** at [console.anthropic.com](https://console.anthropic.com)
   if you don't have one. This is what pays for the AI summaries — costs
   are small (Haiku is used, and a run only summarizes *new* articles).
3. **Add the key as a repo secret**: on GitHub, go to
   `Settings → Secrets and variables → Actions → New repository secret`,
   name it `ANTHROPIC_API_KEY`, and paste your key.
4. **Enable GitHub Pages**: `Settings → Pages → Source: Deploy from a
   branch → Branch: main, folder: /docs`.
5. **Trigger the first run manually**: go to the `Actions` tab, select
   "Update naval news digest", click "Run workflow". After it finishes
   (a minute or two), your site will be live at
   `https://<your-username>.github.io/<repo-name>/`.

```bash
cd naval-news-site
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

## Running it locally (optional, for testing)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...

# sanity-check that every feed URL still responds
python fetch_and_digest.py --check-feeds

# pull new articles and summarize them (limit to 3 while testing, to save API cost)
python fetch_and_digest.py --limit 3

# rebuild the static site
python build_site.py

# open docs/index.html in your browser to preview
```

## Maintaining it

- **Feeds go stale.** News sites occasionally change their RSS URLs.
  Run `python fetch_and_digest.py --check-feeds` every so often; anything
  marked `NO ENTRIES / FAILED` needs a new URL — search "[site name] RSS
  feed" or check `<sitename>.com/feed`. Update the address in
  `feeds.json`.
- **Add or remove sources** by editing `feeds.json`. Keep the `greek` and
  `international` lists roughly balanced if you want the site to stay
  half-and-half.
- **Change the schedule** by editing the `cron` line in
  `.github/workflows/update.yml` (currently every 6 hours, in UTC).
- **Tune what counts as "on topic"** by editing the `KEYWORDS` list near
  the top of `fetch_and_digest.py`.
- **Costs**: only *new* articles get sent to Claude, and it uses the
  Haiku model, so a typical run (a handful of new articles across 9
  feeds, 4x/day) costs a small fraction of a cent to a few cents a day.
  Watch usage at console.anthropic.com if you want to keep an eye on it.

## Files

```
naval-news-site/
├── feeds.json              # your RSS source list (Greek + international)
├── fetch_and_digest.py     # pulls feeds, filters, summarizes via Claude
├── build_site.py           # renders the static site into /docs
├── requirements.txt
├── templates/index.html    # page template (Jinja2)
├── static/style.css        # site styling
├── data/articles.db        # created automatically on first run
├── docs/                   # generated site — this is what GitHub Pages serves
└── .github/workflows/update.yml   # the automation
```
