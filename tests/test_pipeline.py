"""End-to-end run on a tiny synthetic data folder (no real people or companies)."""
from pathlib import Path

import pandas as pd

from warmpath.__main__ import run

NOTES = ('Notes:\n"When exporting your connection data, you may notice that some of the email '
         'addresses are missing."\n\n')
HEADER = "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"


def _export(path, rows):
    path.write_text(NOTES + HEADER + "\n".join(",".join(r) for r in rows) + "\n", encoding="utf-8")


def _make_data(tmp_path):
    data = tmp_path / "data"
    for sub in ("connections", "introducers", "customers"):
        (data / sub).mkdir(parents=True)
    _export(data / "connections" / "LinkedIn Connections- Alice.csv", [
        ["Priya", "Varkhede", "https://www.linkedin.com/in/priya-v", "", "Zorbex Infraprojects Ltd",
         "Head of Procurement", "12-Mar-15"],                      # works at target company
        ["Carol", "Menon", "https://www.linkedin.com/in/carol-m", "", "Menon Advisory",
         "Partner", "01 Jan 2012"],                                # the introducer herself
    ])
    _export(data / "connections" / "Bob.csv", [
        ["Tarun", "Quillan", "https://www.linkedin.com/in/tarun-q", "", "Quillan Gensets Pvt Ltd",
         "Managing Director", "5 Jun 2019"],                       # the target person, 1st degree
    ])
    _export(data / "introducers" / "Carol.csv", [
        ["Nikhil", "Oberstein", "https://www.linkedin.com/in/nikhil-o", "", "Obers Power Systems",
         "CEO", "3 Feb 2016"],                                     # target person via Carol
        ["Lata", "Ferreira", "https://www.linkedin.com/in/lata-f", "", "Ferrolux Energy Pvt Ltd",
         "General Manager - Projects", "3 Feb 2016"],              # insider via Carol
    ])
    customers = pd.DataFrame([
        ["", "Customer database", "", ""],
        ["#", "NAME OF COMPANY", "CONTACT PERSON & DESIGTION", "LOCATION"],
        ["1", "QUILLAN GENSETS PRIVATE LIMITED", "Mr. Tarun Quillan (MD)\n9820000000", "Pune"],
        ["2", "Zorbex Infraprojects Limited", "Sameer Dalvi - GM Electrical", "Mumbai"],
        ["3", "Obers Power Systems", "Nikhil Oberstein, CEO", "Delhi"],
        ["4", "Ferrolux Energy", "Rakesh Iyer", "Surat"],
        ["5", "Unreachable Widgets Co", "Some Body", "Goa"],
        ["6", "Halvorsen Pumps", "Ingrid Halvorsen", "Chennai"],
    ])
    customers.to_excel(data / "customers" / "prospects.xlsx", sheet_name="1. Data Base", header=False, index=False)
    pd.DataFrame([["Summary only"]]).to_excel(data / "customers" / "ignored_summary.xlsx",
                                             sheet_name="Summary", header=False, index=False)
    pd.DataFrame([{"target_name": "Ingrid Halvorsen", "target_company": "Halvorsen Pumps",
                   "target_linkedin_url": "", "checked_by": "Alice", "degree_shown": "2nd",
                   "mutual_connections": "Ola Nordmann", "checked_on": "2026-10-01"}]
                 ).to_csv(data / "mutual_checks.csv", index=False)
    return data


def test_pipeline_finds_every_path_type(tmp_path):
    data = _make_data(tmp_path)
    out_file = run(data, tmp_path / "out", log=lambda *_: None)
    best = pd.read_excel(out_file, sheet_name="Best path per company").set_index("company")

    assert best.loc["QUILLAN GENSETS PRIVATE LIMITED", "best_path"] == "DIRECT"
    assert best.loc["QUILLAN GENSETS PRIVATE LIMITED", "ask_team_member"] == "Bob"

    assert best.loc["Zorbex Infraprojects Limited", "best_path"] == "INSIDER"
    assert best.loc["Zorbex Infraprojects Limited", "via_colleague"] == "Priya Varkhede"

    # Carol is found in Alice's network, so Alice is the one to ask.
    assert best.loc["Obers Power Systems", "best_path"] == "INTRODUCER"
    assert best.loc["Obers Power Systems", "ask_team_member"] == "Alice"
    assert best.loc["Obers Power Systems", "via_introducer"] == "Carol"

    assert best.loc["Ferrolux Energy", "best_path"] == "INTRODUCER_INSIDER"
    assert best.loc["Halvorsen Pumps", "best_path"] == "VERIFIED"
    assert best.loc["Unreachable Widgets Co", "best_path"] == "COLD"

    classified = pd.read_excel(out_file, sheet_name="Connections (classified)")
    assert set(classified["owner"]) == {"Alice", "Bob", "Carol"}
    assert "tier" in classified.columns and "sector" in classified.columns


def test_relationships_file_overrides_auto_link(tmp_path):
    data = _make_data(tmp_path)
    pd.DataFrame([{"introducer": "Carol", "team_member": "Bob", "relationship": "ex-colleague",
                   "strength_1to5": 5, "will_intro": "Y"}]).to_csv(data / "relationships.csv", index=False)
    out_file = run(data, tmp_path / "out", log=lambda *_: None)
    best = pd.read_excel(out_file, sheet_name="Best path per company").set_index("company")
    assert best.loc["Obers Power Systems", "ask_team_member"] == "Bob"
