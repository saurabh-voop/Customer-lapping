# Customer-lapping: warm paths into customer accounts

For every company and contact in the PEIPL customer / prospect workbooks, this finds
**who in the team has the closest path to them**. The aim is to reach people through
someone they know rather than cold.

```
Kapil ──1st──> Customer contact                                   DIRECT          (1st)
Atul ───1st──> Director of the customer (MCA records)              BOARD_DIRECT    (1st)
Vishal ─1st──> Connection who sits on another board WITH that
               customer director                                   CO_DIRECTOR     (2nd)
Sagar ──1st──> Colleague at the customer company ──> contact       INSIDER         (2nd, inferred)
Kapil ──1st──> Connection at a company the customer's director
               also runs ──> director                              SISTER_COMPANY  (2nd, inferred)
Vishal ─1st──> Introducer ─1st──> Customer contact                 INTRODUCER      (2nd)
Atul ───1st──> Introducer ──> Colleague ──> Contact                INTRODUCER_INSIDER (3rd)
```

> **Privacy: this repository is public.** Customer data, phone numbers, LinkedIn exports
> and director data go in `data/`, results in `output/`. Both are git-ignored. Never
> commit them. Consider making the repository private.

## Quick start

```bash
pip install -r requirements.txt
python -m warmpath            # reads ./data, writes ./output/warm_paths_<date>.xlsx
python -m pytest              # optional: run the tests
```

## Folder layout

```
data/
  connections/        LinkedIn exports of TEAM members (Kapil.csv, Vishal.csv, Sagar.csv, Atul.xlsx ...)
  customers/          every customer / prospect workbook (.xlsx / .csv)
  directors.csv       company directors from MCA records (optional, template in templates/)
  introducers/        LinkedIn exports of friends / partners willing to introduce (optional)
  relationships.csv   who each introducer knows in the team (optional, template in templates/)
```

- The owner's name is taken from the file name. "LinkedIn Connections- Kapil.csv" becomes `Kapil`. Atul's Excel file is also read: the script uses its sheet "All Decision-Makers".
- Customer workbooks need no fixed layout. The header row is found by keywords (company / customer / consignee, contact person, designation, email, mobile, LinkedIn, location ...).
  - Summary and pivot tabs are skipped.
  - So is the raw "VOLZA (FULL)" shipment dump, because its companies are already in the Volza Shipper / Cons tabs.
  - The FOCUS city grid is read as companies listed under each city.

## How 2nd and 3rd degree are found

LinkedIn **never exports 2nd or 3rd-degree connections**. Its data export contains only
your own 1st-degree list. Scraping is against LinkedIn's User Agreement §8.2: LinkedIn has
won cases against scrapers, and Proxycurl was shut down in 2025. So 2nd and 3rd degree
come from legal sources the tool can join together:

1. **Shared company boards (`directors.csv`).** Indian company directors are public on the
   MCA portal, along with each director's other directorships (via their DIN).
   - Small promoter-run companies usually have 2–4 directors, often family or co-founders,
     who know each other well. Research on interlocking directorates treats a shared
     director as a real channel between firms (Mizruchi 1996).
   - A team connection counts as a director only when **the names match and** their
     LinkedIn employer is one of that director's companies. This stops common names
     from creating false links.
   - Ranking factors:
     - smaller boards rank higher (≤4 directors ×1.1, >8 ×0.8)
     - terms that overlapped in time rank higher than terms that never overlapped
   - Sources for the file:
     - MCA "View Director Master Data": free, one record at a time.
     - Licensed MCA data APIs (Surepass, Probe42, Tofler) for bulk.
     - Manual research.
   - Every row keeps a `source` column.
2. **Colleagues at the customer company** (from the team's own LinkedIn exports).
3. **Introducers.** These are friends or partners who share their `Connections.csv` in
   `data/introducers/`, plus a row in `relationships.csv` with the columns `introducer,
   team_member, relationship, strength_1to5, will_intro`.

## How matching and scoring work

**Company matching** produces these levels:

| Level | Confidence | Meaning |
|---|---|---|
| exact | 0.95 | Same name once legal suffixes are removed |
| core | 0.85 | Same name once generic words are also removed (Engineering, Infra, Projects, India ...) |
| fuzzy | 0.80 | Typos |
| group | 0.55 | Same group, or same brand in another country |
| loose | 0.40 | Only a name prefix is shared. Always flagged for checking |

Common brand words such as Shree, Aditya, Advance or Tata never match on their own.

**Person matching** happens only inside a matched company, or on an identical LinkedIn URL
or email. It handles initials, reversed name order, middle names and multi-person cells.
Name-only matches across different companies were tested and dropped as mostly wrong.

**Path score** = base for the path type × match confidence × tie factors.

| Path type | Base |
|---|---|
| DIRECT | 100 |
| BOARD_DIRECT | 95 |
| INTRODUCER | 70 |
| CO_DIRECTOR | 65 |
| INSIDER | 55 |
| SISTER_COMPANY | 45 |
| INTRODUCER_INSIDER | 30 |

- **Tie age** (from *Connected On*):
  - under 1 year: ×0.85
  - 3–8 years: ×1.1
  - over 8 years: ×1.15
- **For insiders and sister companies:**
  - seniority: ×1.2 for Chairman/MD/CEO, down to ×0.85 for junior staff
  - ×1.1 for buying functions (procurement, projects, electrical, EPC ...)
- **Board size and term overlap** apply to shared-board paths.

Research on LinkedIn (Rajkumar et al., *Science* 2022) found that strong ties matter more
in less-digital, trust-based industries such as power and EPC.

## Output workbook (filter-ready)

| Sheet | Use |
|---|---|
| Summary | Companies by best path type |
| Best path per company | One row per company: who to ask, through whom, confidence, score |
| Person-level paths | DIRECT / BOARD_DIRECT / CO_DIRECTOR / INTRODUCER paths to named people |
| All paths | Every path found, including alternatives |
| To review (low confidence) | Matches to check before use |
| Cold companies | No path found yet |
| Director data coverage | Customers with and without director data, plus the directors found |
| Paths per team member | Who holds the most paths |
| Connections (classified) | Every connection tagged with Sector and Tier, as in Atul's sheet, plus tiers 4–6 |
| Connector overlap | How many connections each pair of team members shares |
| Input files | Rows read per workbook and sheet |

## Known data issues

- In "1. Business Way-Forward.xlsx" every **"NA" was deleted** from the Volza, FULL DATA
  and Exports tabs, and partly from other tabs. "INTERNATIONAL" became "INTERTIOL".
  - The script repairs common company words.
  - Damaged person names cannot be repaired. Restoring the sheet from an older version
    would improve matches.
- LinkedIn shows a person's current employer. Customer sheets may be out of date.
- Director data gathered from web search snippets can be incomplete. Check DINs on the
  MCA portal before relying on a path.
