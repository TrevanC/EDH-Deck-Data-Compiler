# Bulk EDH Decklists Harvester — System Design & Setup

This document outlines a practical, respectful way to gather **public** Commander/EDH decklists at scale from community sites, normalize the card data, and make it queryable for research and recommendations — without writing code here.

---

## 1) Goals & Non‑Goals
**Goals**
- Collect large volumes of **public** EDH decklists.
- Keep the process **polite, rate‑limited, and ToS‑aware**.
- Normalize cards to stable IDs (Scryfall `oracle_id`) for analysis.
- Support incremental refresh (daily/weekly) and reproducibility.

**Non‑Goals**
- Accessing private/unlisted decks.
- Mirroring entire sites or scraping aggressively.

---

## 2) Sources & Access Strategy
**Primary**
- **Archidekt**: Public, read‑friendly JSON endpoints for decks (paginated). Use format filter for Commander to pull in bulk. Ideal as the main firehose.
- **Moxfield**: Public decks discoverable via site search/browse; per‑deck “export” responses for cardlists. Expect Cloudflare; plan for conservative rates and a headless‑browser fallback.

**Optional (for breadth beyond EDH or for tournament lists)**
- MTGGoldfish / MTGTop8 (tournament decks); TopDeck.gg / Spicerack APIs for structured events. Use sparingly and politely.
- EDHREC for **guidance** (popular commanders, themes) — not a raw deck source.

---

## 3) High‑Level Architecture
- **Ingestion adapters** per source (Archidekt, Moxfield): fetch public data and upsert into storage.
- **Normalization stage**: map card names → Scryfall `oracle_id` using the **Oracle bulk** dump.
- **Storage**: start with SQLite for simplicity; easy upgrade path to Postgres.
- **Orchestration**: cron (or a single job runner) with per‑source schedules + retry/backoff.
- **Outputs**: a simple query interface (CLI/REST) and optional similarity index for recommendations.

```
[Archidekt] ┐                  ┌─> [Decks]
[Moxfield]  ├─> [Adapters] ────┼─> [DeckCards]
            │                  └─> [Sources]
            └─> [Queue] ─────────> [Logs/Metrics]
                         └─> [Normalization (Scryfall oracle bulk)] ──> [oracle_id on DeckCards]
```

---

## 4) Data Model (minimal but effective)
**sources**
- `id`, `name`

**decks**
- `id`, `source_id`, `source_deck_id` (unique per source)
- `format` (e.g., Commander), `title`, `author`, `url`
- `extra` (JSON for source‑specific bits), `created_at`, `updated_at`

**deck_cards**
- `deck_id`, `name`, `qty`, `oracle_id` (nullable until normalized)
- Optional: `zone` (main/side/command) if available; for EDH, capture **commander(s)** explicitly (e.g., a flag or separate table `deck_commanders(deck_id, oracle_id)`).

**indexes**
- `decks(format)`, `deck_cards(oracle_id)`, composite `(source_id, source_deck_id)`.

---

## 5) Normalization Design (Scryfall Oracle Bulk)
- Download **Oracle bulk** JSON (one record per unique card face). Cache locally.
- Build a resolver: `name → oracle_id`, with handling for:
  - DFC/split/adventure/transform cards (map by face name and by full name).
  - Promo/alt names, ‘//’ separators, punctuation, diacritics.
  - Basic lands synonyms; tokens ignored unless you need them.
- Apply resolver to `deck_cards`; log any unmapped names to a review table.
- Re‑run normalization whenever bulk file is refreshed.

---

## 6) Ingestion Workflows
**Archidekt ETL**
- Paginate through public Commander decks (tunable page size & max pages).
- For each deck: upsert `decks`, then `deck_cards` with raw names/qty.
- Respect a global **rate limit** (e.g., ~1 req/sec) and incremental runs.

**Moxfield Discovery + Export**
- **Discovery**: queue public deck IDs via browse/search (e.g., by format or seeding popular commanders). Store IDs in a **work queue** with de‑dupe.
- **Export**: fetch each deck’s public export; parse list; upsert.
- Handle Cloudflare with:
  - Conservative request pacing and jitter.
  - Realistic headers (browser UA), cookie jar.
  - **Headless browser** fallback if HTTP fails reliably.

**Incrementality**
- Track `last_seen_at`/`fetched_at` per deck; only refresh when needed.
- Nightly Archidekt pass; daily/weekly Moxfield updates.

---

## 7) Politeness, Compliance, & Safety
- **Public decks only**; no login or bypass of protections.
- **Rate limits**: start ~0.5–1.5 req/sec per host; add random jitter.
- Exponential backoff on 429/5xx; cool‑off after bursts of errors.
- Cache responses (short‑lived) to reduce re‑hits and to aid retries.
- Identify your client via UA string; include contact URL/email in README.
- Provide an **opt‑out/takedown** path if you publish any datasets derived from the crawl; attribute sources and deck authors when you display.

---

## 8) Orchestration & Scheduling
- **Single‑host cron** is fine initially:
  - `00:00` UTC – Archidekt incremental.
  - `02:00` UTC – Moxfield discovery.
  - `03:00` UTC – Moxfield export worker (N items or time‑boxed).
  - `04:00` UTC – Scryfall refresh + normalization delta.
- All jobs write structured logs + counters (requests, successes, failures, 429s).
- Optional: upgrade to a job runner (Arq/Temporal/Airflow) when scaling.

---

## 9) Storage & Scaling
- **Phase 1**: SQLite (WAL mode) on disk; periodic VACUUM; indexes above.
- **Phase 2**: Postgres for concurrency/scale; partition `deck_cards` by `deck_id` range or hash; add materialized views for common queries.
- **Analytics**: snapshot to **Parquet** for quick offline analysis; keep an export job.

---

## 10) Data Quality & Validation
- EDH sanity checks: ~100 cards (commander(s) + 99), allow duplicates for basic lands, detect obviously broken lists.
- Commander identity present (if source supplies it) or infer heuristically (first line(s), header markers, or source‑provided commander fields).
- Deduplication heuristic: compute a stable **deck fingerprint** (sorted `(oracle_id, qty)` multiset hash) to spot reposts/minor edits.

---

## 11) Telemetry & Ops
- **Metrics**: requests by host, status code, p95 latency, parse failures, decks ingested, unmapped names.
- **Dashboards**: ingestion health, queue depth, normalization coverage (% with oracle_id).
- **Alerts**: high 429 rate, large drop in new decks/day, resolver miss spike.

---

## 12) Configuration (single YAML)
- Global HTTP: `user_agent`, `timeout`, retries/backoff, cache directory.
- Per‑source: `enabled`, `page_size`, `max_pages`, schedules.
- Moxfield discovery seeds: commanders, formats, max pages.
- Export worker: max concurrency (keep low), inter‑request sleep.
- Scryfall: local bulk path; refresh cadence.
- Storage path/DSN.

---

## 13) Security & Privacy
- No secrets required for public pulls.
- Store only what’s public on the deck page/API.
- If you later expose the data, include **attribution** and respect takedowns.

---

## 14) Output Interfaces (lightweight)
- **CLI**: list decks by commander/author; dump a deck’s cardlist; export to CSV/Parquet.
- **REST**: `/decks?format=Commander&limit=...`, `/decks/{id}`, `/cards/top?format=Commander`.
- **Similarity** (optional): Jaccard or TF‑IDF on `oracle_id` bags; a precomputed nearest‑neighbors index for quick recommendations.

---

## 15) Runbook
**First run**
1. Create data directory and DB; apply schema.
2. Download Scryfall Oracle bulk; build resolver cache.
3. Archidekt initial pass (N pages) to seed a big corpus quickly.
4. Moxfield discovery with a short seed list of popular commanders.
5. Moxfield export worker for discovered IDs (time‑box).
6. Normalize newly added cards; review unmapped names.
7. (Optional) Build a similarity index for demo queries.

**Ongoing**
- Daily Archidekt incremental; Moxfield discovery/export on a schedule.
- Weekly Scryfall refresh + re‑normalize.
- Monitor metrics and adjust rates as needed.

---

## 16) Risks & Mitigations
- **Cloudflare changes**: keep an HTTP and a headless fallback; lower rate.
- **Source HTML/API changes**: isolate adapters; feature flags per source.
- **TOS concerns**: stick to public endpoints; throttle; document contact info.
- **Data drift**: resolver test suite; alerts for rising unmapped rate.

---

## 17) What you’ll need installed
- A recent Python (or your preferred runtime) and a task scheduler (cron/Systemd) — language-agnostic design.
- A small SQLite/Postgres instance.
- Headless browser (Chromium) if you choose the Moxfield fallback route.
- Disk space for cached JSON and Parquet snapshots.

---

## 18) Success Criteria
- **Coverage**: # of unique public EDH decks and monthly growth.
- **Quality**: % cards normalized to `oracle_id`; # of commander‑identified decks.
- **Health**: <1% error rate on pulls; sustained politeness (no bans/blocks).

---

### TL;DR plan
1) Use Archidekt as your bulk backbone (polite pagination).
2) Add Moxfield via discover→export with conservative rates and fallback.
3) Normalize everything with Scryfall oracle bulk.
4) Store clean `(deck, card, oracle_id)` triples + minimal metadata.
5) Schedule small, regular increments; watch metrics; iterate.

