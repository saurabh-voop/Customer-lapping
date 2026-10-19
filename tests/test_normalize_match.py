from warmpath.classify import sector_of, tier_of
from warmpath.match import compare_companies, name_similarity
from warmpath.normalize import (company_core, company_key, linkedin_slug, name_tokens,
                                split_contacts)


def _cmp(a, b):
    return compare_companies(company_key(a), company_core(a), company_key(b), company_core(b))


def test_company_key_strips_legal_suffixes_and_repairs_damaged_words():
    assert company_key("Acme Engineering Pvt. Ltd.") == "acme engineering"
    assert company_key("M/s. ACME ENGINEERING PRIVATE LIMITED") == "acme engineering"
    assert company_key("Zeta Intertiol Ltd") == "zeta international"


def test_company_matching_levels():
    assert _cmp("Kalpavriksh Projects Pvt Ltd", "KALPAVRIKSH PROJECTS LIMITED") == "exact"
    assert _cmp("Kalpavriksh Projects", "Kalpavriksh Limited") == "core"
    assert _cmp("Qwertex Energies Ltd", "QWERTEX ENGERGIES") is not None          # typo
    assert _cmp("Qwertex Saudi Arabia LLC", "Qwertex India") == "group"            # other country
    assert _cmp("Mount Zorbu Millers", "Mount Zorbu Group") == "group"


def test_company_matching_rejects_common_words():
    assert _cmp("Advance Infrastructures", "Advance Paints") is None
    assert _cmp("Aditya Construction", "Aditya Electrical Engineering") is None
    assert _cmp("Tata", "Tata") is None
    assert _cmp("Hydro", "Hydro") is None
    assert _cmp("Unique Infrastructures", "Unique Technology Enterprises") is None


def test_name_similarity_handles_initials_order_and_middle_names():
    assert name_similarity(["ravi", "kumar"], ["ravi", "kumar"]) == 1.0
    assert name_similarity(["r", "kumar"], ["ravi", "kumar"]) >= 0.8
    assert name_similarity(["kumar", "ravi"], ["ravi", "kumar"]) >= 0.85
    assert name_similarity(["ritesh", "chandra", "rajpali"], ["ritesh", "rajpali"]) >= 0.85
    assert name_similarity(["ravi", "kumar"], ["ravi", "sharma"]) == 0.0


def test_split_contacts_messy_cells():
    people = split_contacts("Hitesh Patel (Head SCM EPC Division)\nRitesh Rajpali\n(Sr. Manager)")
    assert [p["name"] for p in people] == ["hitesh patel", "ritesh rajpali"]
    assert "Head SCM" in people[0]["designation"] and "Sr. Manager" in people[1]["designation"]

    people = split_contacts("Mr. Jalal Sulaiman, MD  +218-91-2128477")
    assert [p["name"] for p in people] == ["jalal sulaiman"]
    assert people[0]["phones"]

    people = split_contacts("Dhaval Shah, Kalpesh Joshi, Ambar Patel")
    assert len(people) == 3

    assert split_contacts("Main Team :-") == []


def test_linkedin_slug():
    assert linkedin_slug("https://in.linkedin.com/in/Some-One-123/?trk=x") == "some-one-123"
    assert linkedin_slug("linkedin.com/company/acme") is None
    assert name_tokens("Dr. A. K. Rao") == ["a", "k", "rao"]


def test_tier_and_sector():
    assert tier_of("Managing Director") == "1 - Chairman / MD"
    assert tier_of("Co-Founder & CEO") == "2 - CEO / Founder / Owner / President / ED"
    assert tier_of("Head of Procurement").startswith("4")
    assert sector_of("Acme Gensets Pvt Ltd") == "Gensets / Engines"
