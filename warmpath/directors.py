"""Warm paths through shared company boards (India MCA director records).

Input: data/directors.csv, one row per (company, director) with columns
  company, cin, director_name, din, designation, appointed_on, ceased_on, source
from the MCA portal, a licensed MCA data API, or manual research.

Paths added (company level, the target is a director of the customer company):
  BOARD_DIRECT     a team member is connected to a director of the customer        (1st degree)
  CO_DIRECTOR      a team connection sits on another board with that director     (2nd degree)
  SISTER_COMPANY   a team connection works at another company that director runs  (2nd degree, inferred)
A team connection counts as a director only when the names match AND the connection's
LinkedIn employer is one of that director's companies, so common names cannot create
false links.
"""
from collections import defaultdict

import pandas as pd
from dateutil import parser as dateparser

from .match import COMPANY_CONFIDENCE, compare_companies, name_similarity
from .normalize import clean_text, company_core, company_key, name_tokens

BASE = {"BOARD_DIRECT": 95, "CO_DIRECTOR": 65, "SISTER_COMPANY": 45}
DEGREE = {"BOARD_DIRECT": "1st", "CO_DIRECTOR": "2nd (shared board)",
          "SISTER_COMPANY": "2nd (director's other company)"}
STRONG_LEVELS = ("exact", "core", "fuzzy")


def _date(value):
    text = clean_text(value)
    if not text:
        return None
    try:
        return dateparser.parse(text, dayfirst=True).date()
    except (ValueError, OverflowError):
        return None


def load_directors(path):
    df = pd.read_csv(path, dtype=str).fillna("")
    rows = []
    for rec in df.to_dict("records"):
        name = clean_text(rec.get("director_name"))
        company = clean_text(rec.get("company"))
        if not name or not company:
            continue
        tokens = name_tokens(name)
        din = clean_text(rec.get("din")).lstrip("0")
        rows.append({
            "company": company, "company_key": company_key(company), "company_core": company_core(company),
            "cin": clean_text(rec.get("cin")).upper(),
            "director": name.title(), "tokens": tokens,
            # Without a DIN the same person on two boards is joined by full name only.
            "director_id": f"din:{din}" if din else "name:" + " ".join(tokens),
            "designation": clean_text(rec.get("designation")),
            "appointed": _date(rec.get("appointed_on")), "ceased": _date(rec.get("ceased_on")),
            "source": clean_text(rec.get("source")),
        })
    return pd.DataFrame(rows)


def _overlap(a, b):
    """1.0 overlapping terms, 0.85 unknown, 0.6 terms that never overlapped."""
    if not (a["appointed"] or a["ceased"]) or not (b["appointed"] or b["ceased"]):
        return 0.85
    a0, a1 = a["appointed"] or pd.Timestamp.min.date(), a["ceased"] or pd.Timestamp.max.date()
    b0, b1 = b["appointed"] or pd.Timestamp.min.date(), b["ceased"] or pd.Timestamp.max.date()
    return 1.0 if a0 <= b1 and b0 <= a1 else 0.6


def _board_factor(size):
    return 1.1 if size <= 4 else (1.0 if size <= 8 else 0.8)


class DirectorGraph:
    def __init__(self, directors, team):
        self.d = directors.reset_index(drop=True)
        self.team = team
        self.board = defaultdict(list)            # company_key -> [row idx]
        self.companies_of = defaultdict(set)      # director_id -> {company_key}
        self.core_of = {}
        for idx, rec in self.d.iterrows():
            self.board[rec.company_key].append(idx)
            self.companies_of[rec.director_id].add(rec.company_key)
            self.core_of[rec.company_key] = rec.company_core
        self._block = defaultdict(set)            # first token -> {company_key}
        for key, core in self.core_of.items():
            self._block[(core or key).split()[0]].add(key)
            self._block[key.split()[0]].add(key)
        self._team_by_first = defaultdict(list)
        for idx, key in zip(team.index, team["person_key"]):
            if key:
                self._team_by_first[key.split()[0]].append(idx)
        self._team_by_company_token = defaultdict(list)
        for idx, ck, cc in zip(team.index, team["company_key"], team["company_core"]):
            if ck:
                self._team_by_company_token[(cc or ck).split()[0]].append(idx)
        self._identity = {}
        self._at_company = {}

    def boards_for(self, key, core):
        """Director-data companies that are the same firm as a customer company."""
        out = {}
        candidates = set()
        for token in {(core or key).split()[0] if (core or key) else "", key.split()[0] if key else ""} - {""}:
            candidates |= self._block.get(token, set())
        for cand in candidates:
            level = compare_companies(key, core, cand, self.core_of[cand])
            if level in STRONG_LEVELS:
                out[cand] = level
        return out

    def team_connections_for(self, director_id, tokens):
        """Team connections that are this director (name match + employer is one of their boards)."""
        cache_key = director_id
        if cache_key in self._identity:
            return self._identity[cache_key]
        found = []
        boards = self.companies_of[director_id]
        for idx in self._team_by_first.get(tokens[0] if tokens else "", []):
            conn = self.team.loc[idx]
            if name_similarity(tokens, conn.person_key.split()) < 0.85:
                continue
            for b in boards:
                if compare_companies(conn.company_key, conn.company_core, b, self.core_of[b]) in STRONG_LEVELS:
                    found.append(idx)
                    break
        self._identity[cache_key] = found
        return found

    def team_at_company(self, board_key):
        """Team connections whose LinkedIn employer is this company."""
        if board_key not in self._at_company:
            core = self.core_of[board_key]
            candidates = self._team_by_company_token.get((core or board_key).split()[0], [])
            self._at_company[board_key] = [
                idx for idx in candidates
                if compare_companies(self.team.at[idx, "company_key"], self.team.at[idx, "company_core"],
                                     board_key, core) in STRONG_LEVELS]
        return self._at_company[board_key]

    def paths_for_company(self, target, make_row, insider_factor, tie_factor):
        """target: a representative customer record for the company."""
        out = []
        for board_key, level in self.boards_for(target["company_key"], target["company_core"]).items():
            conf_company = COMPANY_CONFIDENCE[level]
            for di in self.board[board_key]:
                d = self.d.loc[di]
                person_target = {**target, "person": d.director,
                                 "designation": d.designation or "Director (MCA)"}
                for idx in self.team_connections_for(d.director_id, d.tokens):
                    c = self.team.loc[idx]
                    out.append(make_row(person_target, "BOARD_DIRECT", c.owner, "", None, conf_company,
                                        f"{c.full_name} is a director of {d.company} (MCA)",
                                        BASE["BOARD_DIRECT"] * conf_company * tie_factor(c.years_connected),
                                        target_conn=c))
                for other in self.companies_of[d.director_id] - {board_key}:
                    other_board = self.board[other]
                    me = next((self.d.loc[i] for i in other_board if self.d.at[i, "director_id"] == d.director_id), d)
                    for oi in other_board:
                        e = self.d.loc[oi]
                        if e.director_id == d.director_id:
                            continue
                        for idx in self.team_connections_for(e.director_id, e.tokens):
                            c = self.team.loc[idx]
                            score = (BASE["CO_DIRECTOR"] * conf_company * _board_factor(len(other_board))
                                     * _overlap(me, e) * tie_factor(c.years_connected))
                            out.append(make_row(person_target, "CO_DIRECTOR", c.owner, "", c, conf_company,
                                                f"{c.full_name} and {d.director} are both directors of {e.company}",
                                                score))
                    for idx in self.team_at_company(other):
                        c = self.team.loc[idx]
                        size = len(other_board)
                        score = (BASE["SISTER_COMPANY"] * conf_company * _board_factor(size)
                                 * insider_factor(c.position) * tie_factor(c.years_connected))
                        out.append(make_row(person_target, "SISTER_COMPANY", c.owner, "", c, conf_company * 0.8,
                                            f"{c.full_name} works at {c.company}, where {d.director} is a director",
                                            score))
        return out
