"""Entity resolution between customer records and LinkedIn connections.

Two-step, Fellegi-Sunter style: candidates are blocked by company (or by LinkedIn URL /
email), scored, then bucketed into confidence levels that a human can review.
"""
from collections import defaultdict

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from .normalize import (AMBIGUOUS_CORES, company_descriptors, company_places,
                        is_distinctive_core)

# company match levels -> confidence
COMPANY_EXACT, COMPANY_CORE, COMPANY_FUZZY, COMPANY_GROUP, COMPANY_LOOSE = (
    "exact", "core", "fuzzy", "group", "loose")
COMPANY_CONFIDENCE = {COMPANY_EXACT: 0.95, COMPANY_CORE: 0.85, COMPANY_FUZZY: 0.8,
                      COMPANY_GROUP: 0.55, COMPANY_LOOSE: 0.4}


def _compatible(a, b):
    """Two descriptor/place sets are compatible when either is empty or they overlap."""
    return not a or not b or bool(a & b)


def compare_companies(key, core, cand_key, cand_core):
    """Return a match level for two normalised company names, or None."""
    if not key or not cand_key:
        return None
    if key == cand_key:
        # A one-word name must itself be distinctive ("Wabag" yes, "Hydro" no).
        specific = len(key.split()) >= 2 or is_distinctive_core(core)
        return COMPANY_EXACT if specific and key not in AMBIGUOUS_CORES else None
    if not is_distinctive_core(core) or not cand_core:
        return None
    same_place = _compatible(company_places(key), company_places(cand_key))
    if cand_core == core:
        if len(core.split()) == 1:
            # "Aditya Construction" vs "Aditya Electrical": same word, different business.
            d1, d2 = company_descriptors(key), company_descriptors(cand_key)
            if not _compatible(d1, d2):
                return None
            if not (d1 & d2) and len(core) < 7:   # "Waaree" vs "Waaree Energies": plausible, unproven
                return COMPANY_GROUP
        return COMPANY_CORE if same_place else COMPANY_GROUP
    if min(len(key), len(cand_key)) >= 6 and fuzz.token_sort_ratio(key, cand_key) >= 92:
        return COMPANY_FUZZY if same_place else COMPANY_GROUP
    # One core is the start of the other: "Mount Meru" vs "Mount Meru Millers" -> same group.
    short, long_ = sorted((core.split(), cand_core.split()), key=len)
    if len(short) < len(long_) and long_[:len(short)] == short and is_distinctive_core(" ".join(short)):
        if len(short) >= 2:
            return COMPANY_GROUP
        if len(short[0]) >= 6:
            return COMPANY_LOOSE
    return None


class CompanyIndex:
    """Maps a target company to connection company keys that plausibly mean the same firm."""

    def __init__(self, connections):
        self.by_key = defaultdict(list)       # company_key -> [row idx]
        self.core_of = {}
        self.block = defaultdict(set)         # first core token -> {company_key}
        for idx, key, core in zip(connections.index, connections["company_key"], connections["company_core"]):
            if not key:
                continue
            self.by_key[key].append(idx)
            self.core_of[key] = core
            for token in set((core or key).split()[:1]):
                self.block[token].add(key)
        self._cache = {}

    def match(self, key, core, aliases=()):
        """Return {connection_company_key: level}."""
        cache_key = (key, core, tuple(aliases))
        if cache_key in self._cache:
            return self._cache[cache_key]
        found = {}
        if key in self.by_key:
            level = compare_companies(key, core, key, core)
            if level:
                found[key] = level
        for alias in aliases:
            if alias in self.by_key:
                found.setdefault(alias, COMPANY_EXACT)
        if core:
            for cand in self.block.get(core.split()[0], ()):
                if cand not in found:
                    level = compare_companies(key, core, cand, self.core_of.get(cand, ""))
                    if level:
                        found[cand] = level
        self._cache[cache_key] = found
        return found


def _same_name_token(a, b):
    if a == b:
        return True
    if len(a) == 1 or len(b) == 1:            # initial vs full name
        return a[0] == b[0]
    return min(len(a), len(b)) >= 4 and JaroWinkler.similarity(a, b) >= 0.92


def name_similarity(target_tokens, conn_tokens):
    """Score 0..1 for two tokenised person names (handles initials and reversed order)."""
    t, c = list(target_tokens), list(conn_tokens)
    if not t or not c:
        return 0.0
    if t == c:
        return 1.0
    if len(t) == 1 or len(c) == 1:
        # Only a first name on one side ("Avinash"): weak evidence, needs same company.
        single, other = (t, c) if len(t) == 1 else (c, t)
        return 0.6 if len(single[0]) >= 4 and single[0] == other[0] else 0.0
    tf, tl, cf, cl = t[0], t[-1], c[0], c[-1]
    if _same_name_token(tf, cf) and _same_name_token(tl, cl):
        initials = len(tf) == 1 or len(cf) == 1 or len(tl) == 1 or len(cl) == 1
        exact = tf == cf and tl == cl
        return 0.97 if exact else (0.8 if initials else 0.9)
    if _same_name_token(tf, cl) and _same_name_token(tl, cf):   # surname written first
        return 0.85
    # "Ritesh Chandra Rajpali" vs "Ritesh Rajpali": match on first + any later token.
    if tf == cf and (set(t[1:]) & set(c[1:])):
        return 0.85
    return 0.0
