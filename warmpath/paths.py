"""Build and score warm-introduction paths from team members to every target.

Path types (best first):
  DIRECT          team member is 1st-degree connected to the target person        (1st degree)
  VERIFIED        team member saw the target as 2nd degree on LinkedIn and named
                  the mutual connection (data/mutual_checks.csv)                  (2nd degree)
  INTRODUCER      a friend/partner who exported their connections (data/introducers)
                  is 1st-degree connected to the target                           (2nd degree)
  INSIDER         team member is connected to someone else at the target company
                  who can introduce internally ("company bridge")                 (2nd degree, inferred)
  INTRODUCER_INSIDER  introducer knows someone at the target company              (3rd degree, inferred)
"""
from collections import defaultdict

import pandas as pd

from .classify import is_buyer_function, tier_of, tier_rank
from .match import COMPANY_CONFIDENCE, CompanyIndex, name_similarity
from .normalize import clean_text, company_key, linkedin_slug, name_tokens, person_key

BASE_SCORE = {"DIRECT": 100, "VERIFIED": 80, "INTRODUCER": 70, "INSIDER": 55, "INTRODUCER_INSIDER": 30}
DEGREE = {"DIRECT": "1st", "VERIFIED": "2nd (verified)", "INTRODUCER": "2nd",
          "INSIDER": "2nd (via colleague)", "INTRODUCER_INSIDER": "3rd (via colleague)"}


def tie_factor(years):
    """Older connections are more likely real relationships than recent cold accepts."""
    if years is None or pd.isna(years):
        return 1.0
    if years < 1:
        return 0.85
    if years < 3:
        return 1.0
    if years < 8:
        return 1.1
    return 1.15


def insider_factor(position):
    """Senior insiders and people in buying functions can route an introduction best."""
    rank = tier_rank(tier_of(position))
    seniority = {1: 1.2, 2: 1.2, 3: 1.1, 4: 1.1, 5: 1.0}.get(rank, 0.85)
    return seniority * (1.1 if is_buyer_function(position) else 1.0)


def confidence_label(conf):
    if conf >= 0.85:
        return "High"
    if conf >= 0.55:
        return "Medium"
    return "Low - check"


def introducer_links(team, introducers, relationships):
    """{introducer_owner: [(team_member, strength 1-5, how_known)]}.

    Uses data/relationships.csv when present; otherwise looks for the introducer's own
    name in each team member's connection list.
    """
    links = defaultdict(list)
    if relationships is not None and not relationships.empty:
        for rec in relationships.to_dict("records"):
            intro = clean_text(rec.get("introducer"))
            member = clean_text(rec.get("team_member"))
            if not intro or not member:
                continue
            if clean_text(rec.get("will_intro")).upper().startswith("N"):
                continue
            try:
                strength = int(float(rec.get("strength_1to5") or 3))
            except ValueError:
                strength = 3
            links[intro.lower()].append((member, max(1, min(strength, 5)),
                                         clean_text(rec.get("relationship")) or "relationships.csv"))
    team_names = defaultdict(set)
    for owner, key in zip(team["owner"], team["person_key"]):
        team_names[key].add(owner)
    for intro in introducers["owner"].unique() if not introducers.empty else []:
        if intro.lower() in links:
            continue
        key = person_key(intro)
        matched = [m for k, owners in team_names.items() for m in owners
                   if k == key or (len(key.split()) == 1 and k.split()[:1] == key.split())]
        for member in sorted(set(matched)):
            links[intro.lower()].append((member, 3, "found in team member's LinkedIn"))
        if not matched:
            links[intro.lower()].append(("(ask: who knows them?)", 2, "no relationship recorded"))
    return links


class PathFinder:
    def __init__(self, team, introducers, relationships=None, mutual_checks=None):
        self.team = team.reset_index(drop=True)
        self.introducers = introducers.reset_index(drop=True)
        self.links = introducer_links(self.team, self.introducers, relationships)
        self.layers = {"team": self.team, "introducer": self.introducers}
        self.company_index = {name: CompanyIndex(df) for name, df in self.layers.items()}
        self.by_slug = {name: _group(df, "slug") for name, df in self.layers.items()}
        self.by_email = {name: _group(df, "email") for name, df in self.layers.items()}
        self.mutual_checks = mutual_checks

    # -- matching ---------------------------------------------------------------------------
    def _person_hits(self, layer, target, company_matches):
        """Connections in `layer` that are the target person -> {row idx: (confidence, how)}."""
        df = self.layers[layer]
        hits = {}
        if target["slug"]:
            for idx in self.by_slug[layer].get(target["slug"], []):
                hits[idx] = (1.0, "same LinkedIn URL")
        for email in target["emails"]:
            for idx in self.by_email[layer].get(email, []):
                hits.setdefault(idx, (1.0, "same email"))
        tokens = target["person_tokens"]
        if tokens:
            for ckey, level in company_matches.items():
                for idx in self.company_index[layer].by_key[ckey]:
                    if idx in hits:
                        continue
                    sim = name_similarity(tokens, df.at[idx, "person_key"].split())
                    if sim >= 0.6:
                        conf = round(sim * COMPANY_CONFIDENCE[level], 2)
                        hits[idx] = (conf, f"name {sim:.2f} + company {level}")
        return hits

    def paths_for(self, target):
        out = []
        matches = {layer: self.company_index[layer].match(
            target["company_key"], target["company_core"], target["company_aliases"])
            for layer in self.layers}
        person_hits = {layer: self._person_hits(layer, target, matches[layer]) for layer in self.layers}

        for idx, (conf, how) in person_hits["team"].items():
            c = self.team.loc[idx]
            out.append(self._row(target, "DIRECT", c.owner, "", None, conf, how,
                                 BASE_SCORE["DIRECT"] * conf * tie_factor(c.years_connected),
                                 target_conn=c))
        for idx, (conf, how) in person_hits["introducer"].items():
            c = self.introducers.loc[idx]
            for member, strength, known in self.links.get(c.owner.lower(), []):
                score = BASE_SCORE["INTRODUCER"] * conf * tie_factor(c.years_connected) * (0.6 + 0.1 * strength)
                out.append(self._row(target, "INTRODUCER", member, c.owner, None, conf,
                                     f"{how}; {member}-{c.owner}: {known} (strength {strength})", score,
                                     target_conn=c))

        for layer in ("team", "introducer"):
            df = self.layers[layer]
            for ckey, level in matches[layer].items():
                for idx in self.company_index[layer].by_key[ckey]:
                    if idx in person_hits[layer]:
                        continue
                    c = df.loc[idx]
                    conf = COMPANY_CONFIDENCE[level]
                    base = tie_factor(c.years_connected) * insider_factor(c.position) * conf
                    how = f"works at {c.company} (company match: {level})"
                    if layer == "team":
                        out.append(self._row(target, "INSIDER", c.owner, "", c, conf, how,
                                             BASE_SCORE["INSIDER"] * base))
                    else:
                        for member, strength, known in self.links.get(c.owner.lower(), []):
                            out.append(self._row(target, "INTRODUCER_INSIDER", member, c.owner, c, conf,
                                                 f"{how}; {member}-{c.owner}: {known}",
                                                 BASE_SCORE["INTRODUCER_INSIDER"] * base * (0.6 + 0.1 * strength)))
        return out

    def verified_paths(self, targets):
        """Rows from data/mutual_checks.csv, attached to the matching target records."""
        if self.mutual_checks is None or self.mutual_checks.empty:
            return []
        index = {}
        for t in targets.to_dict("records"):
            index.setdefault((t["company_key"], " ".join(t["person_tokens"])), t)
            if t["slug"]:
                index.setdefault(("slug", t["slug"]), t)
        out = []
        for rec in self.mutual_checks.to_dict("records"):
            slug = linkedin_slug(rec.get("target_linkedin_url"))
            t = index.get(("slug", slug)) if slug else None
            t = t or index.get((company_key(rec.get("target_company")), " ".join(name_tokens(rec.get("target_name")))))
            if t is None:
                continue
            degree = clean_text(rec.get("degree_shown")).lower()
            member = clean_text(rec.get("checked_by"))
            mutuals = [m.strip() for m in clean_text(rec.get("mutual_connections")).split(";") if m.strip()]
            if degree.startswith("1"):
                out.append(self._row(t, "DIRECT", member, "", None, 1.0, "confirmed 1st degree on LinkedIn",
                                     BASE_SCORE["DIRECT"]))
            elif degree.startswith("2"):
                for m in mutuals or ["(mutual not named)"]:
                    out.append(self._row(t, "VERIFIED", member, m, None, 1.0,
                                         f"LinkedIn shows 2nd degree via {m} (checked {clean_text(rec.get('checked_on'))})",
                                         BASE_SCORE["VERIFIED"]))
        return out

    @staticmethod
    def _row(target, path_type, member, introducer, insider, conf, how, score, target_conn=None):
        return {
            "target_id": target["target_id"],
            "company": target["company"],
            "company_key": target["company_key"],
            "target_person": target["person"],
            "target_designation": target["designation"],
            "location": target.get("location", ""),
            "segment": target.get("segment", ""),
            "source": target["source"],
            "path_type": path_type,
            "degree": DEGREE[path_type],
            "ask_team_member": member,
            "via_introducer": introducer,
            "via_colleague": insider.full_name if insider is not None else "",
            "via_colleague_position": insider.position if insider is not None else "",
            "via_colleague_tier": insider.tier if insider is not None else "",
            "via_colleague_linkedin": insider.url if insider is not None else "",
            "target_linkedin": target_conn.url if target_conn is not None else "",
            "target_current_position": target_conn.position if target_conn is not None else "",
            "years_connected": (insider if insider is not None else target_conn).years_connected
            if (insider is not None or target_conn is not None) else None,
            "match_confidence": round(conf, 2),
            "confidence": confidence_label(conf),
            "score": round(score, 1),
            "why": how,
        }


def _group(df, column):
    groups = defaultdict(list)
    for idx, value in zip(df.index, df[column]):
        if isinstance(value, str) and value:
            groups[value].append(idx)
    return groups
