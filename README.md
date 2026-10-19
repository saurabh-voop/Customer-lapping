# Customer-lapping: warm paths into customer accounts

For every company and contact in the PEIPL customer / prospect workbooks, this finds
**who in the team has the closest LinkedIn path to them**. The aim is to reach people
through someone they know rather than cold.

```
Kapil ──1st──> Customer contact                         DIRECT          (1st degree)
Vishal ─1st──> Introducer ─1st──> Customer contact      INTRODUCER      (2nd degree)
Sagar ──1st──> Colleague at customer co. ──> Contact     INSIDER         (2nd, inferred)
Atul ───1st──> Introducer ──> Colleague ──> Contact      INTRODUCER_INSIDER (3rd, inferred)
Vishal checked LinkedIn: 2nd degree via <named mutual>   VERIFIED        (2nd, confirmed)
```

> **Privacy: this repository is public.** Customer data, phone numbers and LinkedIn
> exports go in `data/` and results in `output/`. Both are git-ignored. Never commit them.
> Consider making the repository private.

## Quick start

```bash
pip install -r requirements.txt
python -m warmpath            # reads ./data, writes ./output/warm_paths_<date>.xlsx
python -m pytest              # optional: run the tests
```

## Folder layout

```
data/
  connections/        LinkedIn exports of TEAM members (Kapil.csv, Vishal.csv, Sagar.csv, Atul.csv ...)
  introducers/        LinkedIn exports of friends / partners willing to introduce (optional)
  customers/          every customer / prospect workbook (.xlsx / .csv)
  relationships.csv   who each introducer knows in the team (optional, template in templates/)
  mutual_checks.csv   results of manual LinkedIn look-ups (optional, template in templates/)
```

- The owner's name is taken from the file name. "LinkedIn Connections- Kapil.csv" becomes `Kapil`. Atul's Excel file is also read: the script uses its sheet "All Decision-Makers".
- Customer workbooks need no fixed layout. The header row is found by keywords (company / customer / consignee, contact person, designation, email, mobile, LinkedIn, location ...).
  - Summary and pivot tabs are skipped.
  - So is the raw "VOLZA (FULL)" shipment dump, because its companies are already in the Volza Shipper / Cons tabs.
  - The FOCUS city grid is read as companies listed under each city.

## What to collect from the team

LinkedIn **never exports 2nd or 3rd-degree connections**. Its data export contains only
your own 1st-degree list. Scraping is against LinkedIn's User Agreement §8.2 and risks
bans on the team's accounts. 2nd and 3rd degree therefore come from three sources:

1. **Full export from each team member.** LinkedIn → Settings → Data privacy → *Get a
   copy of your data* → tick **Connections** → `Connections.csv`.
   - Send it unedited.
   - A list filtered to decision-makers drops purchase heads and project managers, who
     are often the best insiders.
2. **Introducers.** These are trusted friends, ex-colleagues, consultants and channel
   partners who agree to share their `Connections.csv`.
   - Put their exports in `data/introducers/`.
   - Add one row per relationship to `relationships.csv` with the columns `introducer,
     team_member, relationship, strength_1to5, will_intro`.
   - Without a row there, the script looks for the introducer's name in the team's own
     connections.
   - Each introducer makes their 1st-degree network a real 2nd degree for the team.
3. **Manual checks.** The output's "Manual LinkedIn checks" sheet lists named contacts
   with no person-level path.
   - A team member opens each profile and notes the degree LinkedIn shows (1st/2nd/3rd)
     and the names of the mutual connections.
   - The filled rows are saved as `data/mutual_checks.csv`.
   - The next run turns them into VERIFIED paths.

Paid alternative: LinkedIn Sales Navigator **TeamLink** shows 2nd-degree paths through
colleagues. It needs the Advanced plan, and TeamLink Extend needs Advanced / Advanced Plus.
It can't be exported, but it is the best way to double-check the top accounts.

## How matching and scoring work

**Company matching** produces these levels:

| Level | Confidence | Meaning |
|---|---|---|
| exact | 0.95 | Same name once legal suffixes (Pvt Ltd, Limited ...) are removed |
| core | 0.85 | Same name once generic words are also removed (Engineering, Infra, Projects, India ...) |
| fuzzy | 0.80 | Typos |
| group | 0.55 | Same group, or same brand in another country |
| loose | 0.40 | Only a name prefix is shared. Always flagged for checking |

Common brand words such as Shree, Aditya, Advance or Tata never match on their own.

**Person matching** happens only inside a matched company, or on an identical LinkedIn URL
or email. It handles initials ("R. Kumar"), reversed name order, middle names and
multi-person cells such as "A Shah (GM), B Rao / C Iyer". Name-only matches across
different companies were tested and dropped: names like "Praveen Kumar" made them
mostly wrong.

**Path score** = base for the path type (DIRECT 100, VERIFIED 80, INTRODUCER 70,
INSIDER 55, INTRODUCER_INSIDER 30) × match confidence × the factors below.

- **Tie age** (from *Connected On*):
  - under 1 year: ×0.85
  - 3–8 years: ×1.1
  - over 8 years: ×1.15
- **For insiders:**
  - seniority: Chairman/MD/CEO ×1.2, down to junior staff ×0.85
  - ×1.1 for buying functions (procurement, projects, electrical, MEP, EPC ...)
- **For introducers:** relationship strength 1–5 maps to ×0.7–1.1.

Older and stronger ties rank higher. Research on LinkedIn (Rajkumar et al., *Science*
2022) found that strong ties matter more in less-digital, trust-based industries such as
power and EPC. The approach to Indian names, company names and confidence tiers follows
standard record linkage (Fellegi-Sunter).

## Output workbook (filter-ready)

| Sheet | Use |
|---|---|
| Summary | Companies by best path type |
| Best path per company | One row per company: who to ask, through whom, confidence, score |
| Person-level paths | DIRECT / VERIFIED / INTRODUCER paths to named contacts |
| All paths | Every path found, including alternatives |
| To review (low confidence) | Matches to check before use |
| Cold companies | No path found yet |
| Manual LinkedIn checks | Pre-filled `mutual_checks.csv` rows for the team to complete |
| Paths per team member | Who holds the most paths |
| Connections (classified) | Every connection tagged with Sector and Tier, as in Atul's sheet, plus tiers 4–6 |
| Connector overlap | How many connections each pair of team members shares |
| Input files | Rows read per workbook and sheet |

## Known data issues

- In "1. Business Way-Forward.xlsx" every **"NA" was deleted** from the Volza, FULL DATA
  and Exports tabs, and partly from other tabs. "INTERNATIONAL" became "INTERTIOL" and
  "NAME" became "ME", probably through a find-and-replace.
  - The script repairs common company words.
  - Damaged person names, such as "Narendra" turned into "rendra", cannot be repaired.
    Restoring the sheet from an older copy would improve matches.
- LinkedIn shows a person's current employer. Customer sheets may be out of date, so a
  missing match can mean the contact changed jobs.
