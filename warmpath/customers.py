"""Turn messy customer / prospect workbooks into one list of target people and companies.

Headers are detected by keyword, so new workbooks work as long as they have a column
that looks like a company name. Sheet-level skips live in SKIP_SHEET_RE.
"""
import re
from pathlib import Path

import pandas as pd

from .normalize import (EMAIL_RE, clean_text, company_aliases, company_core, company_key,
                        linkedin_slug, name_tokens, split_contacts)

# Pivot/summary tabs, the 37k-row raw shipment dump (its shippers/consignees are already
# de-duplicated in the 'Volza (Shipper)' / 'Volza (Cons)' tabs) and narrative tabs.
SKIP_SHEET_RE = re.compile(r"summary|pivot|volza \(full\)|^table \d|^copy of", re.I)

EXCLUDE_FOR_COMPANY = r"city|state|email|contact|number|address|website|web site|country|intro|type|sector|current|count|b/l|ref"
ROLE_PATTERNS = [
    # (role, include regex, exclude regex) — first matching column per role wins, in this order.
    ("company", r"^(name of company|company name|company|customer|me of company)$", None),
    ("company", r"company|customer|consignee|shipper", EXCLUDE_FOR_COMPANY),
    ("person", r"contact person|person met|key person|^name$|^delegate", r"number|email id$"),
    ("designation", r"designation|^title$|^position$|current title", None),
    ("email", r"e-?mail", r"status|check"),
    ("phone", r"mob|tel|phone|contact number", None),
    ("linkedin", r"linkedin", None),
    ("location", r"^location$|^city$|shipper city|^state$", None),
    ("country", r"country", None),
    ("segment", r"segment|sector|^cat$|type / sector", None),
    ("visited", r"visited", None),
    ("status", r"^status$|latest status|out-?co+me", None),
    ("owner", r"peers to|in charge|b/l name", None),
]


def _norm_header(value):
    return re.sub(r"\s+", " ", clean_text(value).replace("\n", " ")).strip().lower()


def _map_columns(headers):
    mapping = {}
    for role, include, exclude in ROLE_PATTERNS:
        if role in mapping:
            continue
        for idx, header in enumerate(headers):
            if not header or idx in mapping.values():
                continue
            if re.search(include, header) and not (exclude and re.search(exclude, header)):
                mapping[role] = idx
                break
    return mapping


def _find_header(raw, max_scan=15):
    best = (None, {})
    for i in range(min(max_scan, len(raw))):
        headers = [_norm_header(v) for v in raw.iloc[i].tolist()]
        mapping = _map_columns(headers)
        if "company" in mapping and len(mapping) > len(best[1]):
            best = (i, mapping)
    return best


def _focus_grid(raw, source, sheet):
    """'FOCUS' style tab: header row of cities, company names listed under each city."""
    header_row = next((i for i in range(min(10, len(raw)))
                       if sum(bool(clean_text(v)) for v in raw.iloc[i]) >= 4), None)
    if header_row is None:
        return []
    out = []
    cities = [clean_text(v) for v in raw.iloc[header_row]]
    for r in range(header_row + 1, len(raw)):
        for c, city in enumerate(cities):
            if not city or city == "#":
                continue
            name = clean_text(raw.iat[r, c])
            if name and not name.replace(".", "").isdigit():
                out.append({"source": source, "sheet": sheet, "row": r + 1, "company": name,
                            "location": city})
    return out


def _cell(row, mapping, role):
    idx = mapping.get(role)
    return clean_text(row[idx]) if idx is not None and idx < len(row) else ""


def load_workbook(path):
    """Return a list of raw target dicts (one per row) from every useful sheet of a workbook."""
    path = Path(path)
    rows = []
    if path.suffix.lower() == ".csv":
        sheets = {"csv": pd.read_csv(path, header=None, dtype=str)}
    else:
        sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
    for sheet, raw in sheets.items():
        if SKIP_SHEET_RE.search(sheet) or raw.empty:
            continue
        if "focus" in sheet.lower():
            rows.extend(_focus_grid(raw, path.name, sheet))
            continue
        header_idx, mapping = _find_header(raw)
        if header_idx is None:
            continue
        for r in range(header_idx + 1, len(raw)):
            row = raw.iloc[r].tolist()
            company = _cell(row, mapping, "company")
            if not company or company.replace(".", "").isdigit():
                continue
            rec = {"source": path.name, "sheet": sheet, "row": r + 1, "company": company}
            for role in ("person", "designation", "email", "phone", "linkedin", "location",
                         "country", "segment", "visited", "status", "owner"):
                rec[role] = _cell(row, mapping, role)
            rows.append(rec)
    return rows


def explode_people(raw_rows):
    """One record per (company, person). Rows without a usable name keep person=''."""
    out = []
    for rec in raw_rows:
        people = split_contacts(rec.get("person", ""))
        base_emails = EMAIL_RE.findall(rec.get("email", "") or "")
        slug = linkedin_slug(rec.get("linkedin"))
        if not people:
            people = [{"name": "", "designation": "", "emails": [], "phones": []}]
        for i, p in enumerate(people):
            emails = p.get("emails") or []
            if len(people) == 1:
                emails = emails + base_emails
            out.append({
                **{k: v for k, v in rec.items() if k not in ("person", "email", "linkedin", "designation")},
                "company_key": company_key(rec["company"]),
                "company_core": company_core(rec["company"]),
                "company_aliases": sorted(company_aliases(rec["company"])),
                "person": p["name"].title(),
                "person_tokens": name_tokens(p["name"]),
                "designation": (p.get("designation") or (rec.get("designation") if len(people) == 1 else "") or "").strip(),
                "emails": sorted({e.lower() for e in emails}),
                # A LinkedIn URL in the row describes the row's person only when there is one.
                "slug": slug if len(people) == 1 else None,
                "phone": rec.get("phone") or ", ".join(p.get("phones") or []),
            })
    return out


def load_customers(folder):
    """Load every workbook in `folder`; returns (targets DataFrame, per-file stats)."""
    folder = Path(folder)
    raw = []
    stats = []
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        if path.suffix.lower() not in (".xlsx", ".xls", ".csv") or path.name.startswith(("~$", ".")):
            continue
        rows = load_workbook(path)
        stats.append({"file": path.name, "rows": len(rows),
                      "sheets": ", ".join(sorted({r["sheet"] for r in rows}))})
        raw.extend(rows)
    people = pd.DataFrame(explode_people(raw))
    if people.empty:
        return people, pd.DataFrame(stats)
    # The same company/person often appears in several tabs and files: merge them.
    people["target_id"] = people["company_key"] + "|" + people["person_tokens"].map(" ".join)
    agg = {col: "first" for col in people.columns if col not in ("target_id",)}
    agg.update({
        "source": lambda s: "; ".join(sorted(set(s))),
        "sheet": lambda s: "; ".join(sorted(set(s))),
        "row": lambda s: ", ".join(str(x) for x in sorted(set(s))[:5]),
        "emails": lambda s: sorted({e for lst in s for e in lst}),
        "slug": lambda s: next((x for x in s if x), None),
        "designation": lambda s: max(s, key=lambda x: len(x or "")),
        "phone": lambda s: next((x for x in s if x), ""),
    })
    for col in ("location", "segment", "visited", "status", "owner", "country"):
        if col in people.columns:
            agg[col] = lambda s: next((x for x in s if isinstance(x, str) and x), "")
    merged = people.groupby("target_id", as_index=False, sort=False).agg(agg)
    return merged, pd.DataFrame(stats)
