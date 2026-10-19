"""Load LinkedIn connection exports (raw Connections.csv or Atul-style .xlsx)."""
import io
import re
from datetime import date
from pathlib import Path

import pandas as pd
from dateutil import parser as dateparser

from .classify import sector_of, tier_of
from .normalize import clean_text, company_core, company_key, linkedin_slug, person_key

_OWNER_NOISE = re.compile(
    r"linkedin|connections?|decision|makers?|by|sector|export|data|copy|final|"
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|\d+",
    re.I,
)

COLUMNS = ["owner", "first_name", "last_name", "full_name", "person_key", "slug", "url",
           "email", "company", "company_key", "company_core", "position", "connected_on",
           "years_connected", "sector", "tier"]


def guess_owner(path):
    """'LinkedIn Connections- Kapil.csv' -> 'Kapil'; 'Atul.xlsx' -> 'Atul'."""
    stem = Path(path).stem
    words = [w for w in re.split(r"[\s_\-.()]+", _OWNER_NOISE.sub(" ", stem)) if w]
    return " ".join(w.capitalize() for w in words) or stem


def _read_csv(path):
    lines = Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("First Name")), None)
    if start is None:
        raise ValueError(f"{path}: no 'First Name' header row - is this a LinkedIn Connections.csv?")
    return pd.read_csv(io.StringIO("\n".join(lines[start:])), dtype=str)


def _read_xlsx(path):
    book = pd.ExcelFile(path)
    # Prefer a sheet that holds everyone (Atul's file: 'All Decision-Makers').
    for sheet in book.sheet_names:
        df = book.parse(sheet, dtype=str)
        if {"First Name", "Last Name"}.issubset(df.columns):
            if "all" in sheet.lower() or "connections" in sheet.lower():
                return df
    for sheet in book.sheet_names:
        df = book.parse(sheet, dtype=str)
        if {"First Name", "Last Name"}.issubset(df.columns):
            return df
    raise ValueError(f"{path}: no sheet with 'First Name' / 'Last Name' columns")


def _parse_date(value):
    text = clean_text(value)
    if not text:
        return None
    try:
        return dateparser.parse(text, dayfirst=True).date()
    except (ValueError, OverflowError):
        return None


def load_connections(path, owner=None, today=None):
    path = Path(path)
    raw = _read_xlsx(path) if path.suffix.lower() in (".xlsx", ".xls") else _read_csv(path)
    owner = owner or guess_owner(path)
    today = today or date.today()
    rows = []
    for rec in raw.to_dict("records"):
        first, last = clean_text(rec.get("First Name")), clean_text(rec.get("Last Name"))
        if not (first or last):
            continue
        company = clean_text(rec.get("Company"))
        position = clean_text(rec.get("Position"))
        connected = _parse_date(rec.get("Connected On"))
        rows.append({
            "owner": owner,
            "first_name": first,
            "last_name": last,
            "full_name": f"{first} {last}".strip(),
            "person_key": person_key(first, last),
            "slug": linkedin_slug(rec.get("URL")),
            "url": clean_text(rec.get("URL")),
            "email": clean_text(rec.get("Email Address")).lower(),
            "company": company,
            "company_key": company_key(company),
            "company_core": company_core(company),
            "position": position,
            "connected_on": connected,
            "years_connected": round((today - connected).days / 365.25, 1) if connected else None,
            "sector": clean_text(rec.get("Sector")) or sector_of(company, position),
            "tier": tier_of(position),
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def load_folder(folder, today=None):
    """Load every .csv/.xlsx export in a folder. Returns one DataFrame (may be empty)."""
    folder = Path(folder)
    frames = []
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() in (".csv", ".xlsx", ".xls") and not path.name.startswith(("~$", ".")):
                frames.append(load_connections(path, today=today))
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    return pd.concat(frames, ignore_index=True)
