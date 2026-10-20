"""python -m warmpath [--data data] [--out output]

Finds the warmest route from the team to every company and person in the customer
workbooks. See README.md for the folder layout and the files to collect.
"""
import argparse
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from .connections import load_folder
from .customers import load_customers
from .directors import DirectorGraph, load_directors
from .paths import PathFinder, insider_factor, tie_factor
from .report import PERSON_PATHS, best_per_company, connector_overlap, write_workbook


def _optional_csv(path):
    path = Path(path)
    return pd.read_csv(path, dtype=str).fillna("") if path.is_file() else None


def run(data_dir, out_dir, log=print):
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    started = time.time()
    team = load_folder(data_dir / "connections")
    if team.empty:
        sys.exit(f"No LinkedIn exports found in {data_dir / 'connections'} - see README.md")
    introducers = load_folder(data_dir / "introducers")
    log(f"Team connections: {len(team):,} from {', '.join(sorted(team.owner.unique()))}")
    if not introducers.empty:
        log(f"Introducer connections: {len(introducers):,} from {', '.join(sorted(introducers.owner.unique()))}")

    targets, file_stats = load_customers(data_dir / "customers")
    if targets.empty:
        sys.exit(f"No customer rows found in {data_dir / 'customers'} - see README.md")
    log(f"Targets: {len(targets):,} records across {targets.company_key.nunique():,} companies")

    finder = PathFinder(team, introducers,
                        relationships=_optional_csv(data_dir / "relationships.csv"))
    rows = []
    for target in targets.to_dict("records"):
        rows.extend(finder.paths_for(target))

    board_coverage = pd.DataFrame()
    if (data_dir / "directors.csv").is_file():
        directors = load_directors(data_dir / "directors.csv")
        graph = DirectorGraph(directors, team)
        log(f"Director records: {len(directors):,} across {directors.company_key.nunique():,} companies")
        coverage = []
        for target in targets.drop_duplicates("company_key").to_dict("records"):
            boards = graph.boards_for(target["company_key"], target["company_core"])
            coverage.append({"company": target["company"], "source": target["source"],
                             "director_data": "yes" if boards else "no",
                             "directors": ", ".join(sorted({graph.d.at[i, "director"] for b in boards
                                                            for i in graph.board[b]}))})
            if boards:
                rows.extend(graph.paths_for_company(target, PathFinder._row, insider_factor, tie_factor))
        board_coverage = pd.DataFrame(coverage).sort_values("director_data", ascending=False)
    paths = pd.DataFrame(rows)
    if not paths.empty:
        paths = (paths.sort_values("score", ascending=False)
                 .drop_duplicates(["target_id", "target_person", "path_type", "ask_team_member",
                                   "via_introducer", "via_colleague", "target_linkedin"]))

    best = best_per_company(paths, targets)
    summary = (best.groupby(["best_path", "degree"]).size().rename("companies").reset_index()
               .sort_values("companies", ascending=False))
    per_member = (paths.groupby(["ask_team_member", "path_type"]).target_id.nunique()
                  .unstack(fill_value=0).reset_index() if not paths.empty else pd.DataFrame())
    connections = pd.concat([team.assign(layer="team"), introducers.assign(layer="introducer")])

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"warm_paths_{date.today():%Y-%m-%d}.xlsx"
    person_paths = paths[paths.path_type.isin(PERSON_PATHS)] if not paths.empty else paths
    write_workbook(out_file, {
        "Summary": summary,
        "Best path per company": best,
        "Person-level paths": person_paths,
        "All paths": paths,
        "To review (low confidence)": paths[paths.confidence.str.startswith("Low")] if not paths.empty else paths,
        "Cold companies": best[best.best_path == "COLD"],
        "Director data coverage": board_coverage,
        "Paths per team member": per_member,
        "Connections (classified)": connections[[
            "layer", "owner", "sector", "tier", "first_name", "last_name", "company", "position",
            "url", "email", "connected_on", "years_connected"]].sort_values(["owner", "sector", "tier"]),
        "Connector overlap": connector_overlap(connections),
        "Input files": file_stats,
    })
    log(summary.to_string(index=False))
    log(f"Wrote {out_file} in {time.time() - started:.0f}s")
    return out_file


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default="data", help="input folder (default: data)")
    parser.add_argument("--out", default="output", help="output folder (default: output)")
    args = parser.parse_args(argv)
    run(args.data, args.out)


if __name__ == "__main__":
    main()
