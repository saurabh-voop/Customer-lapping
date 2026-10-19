"""Write the team-facing Excel workbook (filters + frozen headers on every sheet)."""
import pandas as pd

PATH_RANK = {"DIRECT": 0, "VERIFIED": 1, "INTRODUCER": 2, "INSIDER": 3, "INTRODUCER_INSIDER": 4}


def best_per_company(paths, targets):
    """One row per target company: the highest-scoring path plus alternatives."""
    companies = (targets.groupby("company_key", sort=False)
                 .agg(company=("company", "first"), source=("source", lambda s: "; ".join(sorted(set("; ".join(s).split("; "))))),
                      location=("location", lambda s: next((x for x in s if x), "")),
                      segment=("segment", lambda s: next((x for x in s if x), "")),
                      named_contacts=("person", lambda s: ", ".join([x for x in s if x][:6])))
                 .reset_index())
    if paths.empty:
        companies["best_path"] = "COLD"
        return companies
    ranked = paths.sort_values(["score"], ascending=False)
    best = ranked.drop_duplicates("company_key")[[
        "company_key", "path_type", "degree", "ask_team_member", "via_introducer", "target_person",
        "via_colleague", "via_colleague_position", "via_colleague_linkedin", "target_linkedin",
        "confidence", "score", "why"]].rename(columns={"path_type": "best_path"})
    stats = paths.groupby("company_key").agg(
        paths_found=("score", "size"),
        team_members_with_path=("ask_team_member", lambda s: ", ".join(sorted(set(s)))),
        direct_contacts=("path_type", lambda s: int((s == "DIRECT").sum())),
        insiders=("path_type", lambda s: int(s.isin(["INSIDER", "INTRODUCER_INSIDER"]).sum())),
    ).reset_index()
    out = companies.merge(best, on="company_key", how="left").merge(stats, on="company_key", how="left")
    out["best_path"] = out["best_path"].fillna("COLD")
    out["degree"] = out["degree"].fillna("none found")
    out["_rank"] = out["best_path"].map(PATH_RANK).fillna(9)
    out = out.sort_values(["_rank", "score"], ascending=[True, False]).drop(columns=["_rank"])
    return out


def connector_overlap(connections):
    owners = sorted(connections["owner"].unique())
    sets = {o: set(connections.loc[connections.owner == o, "slug"].dropna()) for o in owners}
    return pd.DataFrame([[len(sets[a] & sets[b]) for b in owners] for a in owners],
                        index=owners, columns=owners).reset_index().rename(columns={"index": "connections of"})


def manual_check_queue(best, top_n):
    """Companies without a person-level path: ask the team to look them up on LinkedIn."""
    todo = best[~best["best_path"].isin(["DIRECT", "VERIFIED", "INTRODUCER"])].copy()
    todo = todo[todo["named_contacts"].astype(str).str.len() > 0].head(top_n)
    return pd.DataFrame({
        "target_name": todo["named_contacts"].str.split(", ").str[0],
        "target_company": todo["company"],
        "target_linkedin_url": "",
        "checked_by": "",
        "degree_shown": "",
        "mutual_connections": "",
        "checked_on": "",
        "current_best_path": todo["best_path"],
    })


def write_workbook(path, sheets):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df = df.copy()
            for col in df.columns:
                if df[col].map(lambda v: isinstance(v, list)).any():
                    df[col] = df[col].map(lambda v: ", ".join(v) if isinstance(v, list) else v)
            df.to_excel(writer, sheet_name=name[:31], index=False)
            ws = writer.sheets[name[:31]]
            ws.freeze_panes = "A2"
            if len(df.columns):
                ws.auto_filter.ref = ws.dimensions
            for i, col in enumerate(df.columns, start=1):
                sample = df[col].head(200).map(lambda v: len(str(v)))
                width = min(max([len(str(col))] + sample.tolist()) + 2, 60)
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
