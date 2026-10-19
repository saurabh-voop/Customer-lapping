"""Name, company and URL normalisation plus splitting of messy contact cells."""
import re
import unicodedata

LEGAL_SUFFIXES = [
    "private limited", "pvt limited", "pvt ltd", "pvt. ltd", "private ltd",
    "limited", "ltd", "llp", "llc", "inc", "plc", "gmbh", "corporation",
    "corp", "company", "co", "pvt", "private", "pte", "sa", "ag", "bv", "fze", "fzco",
]
# Words that describe *what* a company does rather than *which* company it is.
GENERIC_WORDS = {
    "india", "indian", "group", "the", "and", "of", "engineering", "engineers",
    "engg", "infra", "infrastructure", "infrastructures", "projects", "project",
    "industries", "industry", "enterprises", "enterprise", "solutions", "services",
    "international", "global", "technologies", "technology", "tech", "systems",
    "energy", "energies", "power", "electricals", "electrical", "electric",
    "constructions", "construction", "builders", "developers", "holdings",
    "ventures", "trading", "traders", "works", "consultants", "consulting",
    "associates", "agencies", "products", "manufacturing", "mfg", "renewables",
    "renewable", "green", "solar", "ms", "m s", "division", "team", "tender", "epc",
    "national", "corporate", "office", "head", "unit", "plant", "works",
    "hydro", "water", "wind", "steel", "cement", "chemicals", "logistics", "bank",
    "university", "hospital", "hotel", "motors", "auto", "generators", "transformers",
}
# Places: they tell entities of one group apart (Cummins India vs Cummins Qatar).
PLACE_WORDS = {
    "india", "indian", "hong", "kong", "singapore", "dubai", "uae", "usa", "us", "uk",
    "china", "saudi", "arabia", "qatar", "oman", "kuwait", "bahrain", "kenya", "nigeria",
    "zambia", "tanzania", "ethiopia", "libya", "egypt", "malaysia", "indonesia",
    "vietnam", "thailand", "bangladesh", "nepal", "bhutan", "sri", "lanka", "africa",
    "asia", "pacific", "middle", "east", "europe", "gulf", "spain", "czech", "republic",
    "germany", "italy", "france", "japan", "korea", "delhi", "mumbai", "pune",
    "ahmedabad", "gujarat", "maharashtra", "chennai", "bangalore", "bengaluru",
    "hyderabad", "kolkata", "surat", "vadodara", "baroda", "noida", "gurgaon",
    "gurugram", "ncr", "lusaka", "doha", "riyadh", "jeddah", "sharjah", "abu", "dhabi",
}
# Brand words that are ordinary English / Indian words: on their own they do not
# identify one company ("Advance Infrastructures" vs "Advance Paints").
COMMON_BRAND_WORDS = {
    "tata", "adani", "birla", "aditya", "reliance", "godrej", "mahindra", "jindal",
    "bajaj", "man", "max", "raj", "atul", "sms", "abr", "pioneer", "star", "new",
    "royal", "shree", "shri", "sri", "om", "sai", "jai", "ganesh", "krishna", "bharat",
    "hindustan", "apollo", "united", "standard", "universal", "supreme", "prime",
    "general", "modern", "city", "classic", "perfect", "excel", "self", "freelance",
    "advance", "advanced", "associated", "alliance", "creative", "horizon", "sunshine",
    "trident", "unique", "cosmos", "integrated", "orient", "oriental", "cooper",
    "ministry", "university", "satyam", "shreeji", "tirupati", "balaji", "arihant",
    "mahalaxmi", "laxmi", "lakshmi", "durga", "ambica", "ambika", "shiv", "shiva",
    "hari", "radhe", "jay", "vijay", "ajay", "anand", "kumar", "patel", "shah",
    "metro", "nextgen", "next", "smart", "future", "vision", "victory", "success",
    "galaxy", "sun", "moon", "sky", "ocean", "earth", "eagle", "lion", "tiger",
    "diamond", "gold", "golden", "silver", "crystal", "pearl", "matrix", "fusion",
    "dynamic", "dynamics", "elite", "excellent", "ideal", "reliable", "quality",
    "precision", "accurate", "rapid", "speed", "swift", "first", "one", "best",
    "great", "grand", "mega", "super", "power", "energy", "india", "hotel", "bank",
    "capital", "nippon", "indigo", "pacific", "atlas", "delta", "alpha", "omega",
    "sigma", "beta", "apex", "summit", "zenith", "pinnacle", "unity", "trust",
    "care", "life", "home", "world", "kalyan", "mangal", "shubh", "commercial",
    "central", "continental", "fortune", "pragati", "techno", "maruti", "basant",
    "bharti", "industrial", "marine", "ganga", "yamuna", "narmada", "sagar",
}
AMBIGUOUS_CORES = COMMON_BRAND_WORDS | {"aditya birla", "self employed", "national"}
# Tokens damaged by a bulk "NA" -> "" replace seen in some source sheets.
REPAIRS = {"intertiol": "international", "tiol": "national", "fince": "finance",
           "fincial": "financial"}
HONORIFICS = r"\b(mr|mrs|ms|miss|dr|shri|smt|sri|engr|er|capt|prof|col|lt|cdr|cmde|adv|ca)\b\.?"
DESIGNATION_WORDS = {
    "manager", "mgr", "head", "director", "md", "ceo", "cfo", "coo", "cto", "gm",
    "agm", "dgm", "vp", "avp", "svp", "president", "chairman", "owner", "founder",
    "partner", "engineer", "engr", "executive", "officer", "purchase", "procurement",
    "scm", "sr", "senior", "jr", "junior", "assistant", "asst", "deputy", "dy",
    "general", "chief", "lead", "incharge", "hod", "proprietor", "consultant",
    "accounts", "sales", "marketing", "projects", "project", "electrical",
    "mechanical", "admin", "operations", "planning", "tender", "tendering",
    "commercial", "store", "stores", "site", "plant", "division", "dept",
    "department", "team", "main", "contact", "person", "secretary", "coordinator",
    "supervisor", "technical", "design", "board", "member", "trustee", "chairperson",
    "management", "managing", "whole", "time", "independent", "non", "registered",
    "ref", "reference", "mob", "mobile", "tel", "phone", "email", "office",
}

_SUFFIX_RE = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in sorted(LEGAL_SUFFIXES, key=len, reverse=True)) + r")\b"
)


def ascii_fold(text):
    text = unicodedata.normalize("NFKD", str(text))
    return text.encode("ascii", "ignore").decode("ascii")


def clean_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none", "nat", "-", "--", "na", "n/a") else text


def company_key(name):
    """Full normalised company name: lower-case, punctuation and legal suffixes removed."""
    text = ascii_fold(clean_text(name)).lower()
    text = re.sub(r"\(.*?\)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"^\s*m\s*s\s+", " ", text)  # "M/s." prefix
    text = _SUFFIX_RE.sub(" ", text)
    return " ".join(REPAIRS.get(t, t) for t in text.split())


def company_core(name):
    """Distinctive part of a company name: generic industry words and places removed."""
    tokens = [t for t in company_key(name).split() if t not in GENERIC_WORDS and t not in PLACE_WORDS]
    return " ".join(tokens)


def company_places(key):
    return {t for t in key.split() if t in PLACE_WORDS}


def company_descriptors(key):
    return {t for t in key.split() if t in GENERIC_WORDS and t not in ("the", "and", "of", "ms", "m", "s")}


def company_aliases(name):
    """Extra keys hidden in brackets, e.g. 'Adani Green Energy Ltd (AGEL)' -> {'agel'}."""
    out = set()
    for inner in re.findall(r"\(([^()]*)\)", clean_text(name)):
        key = company_key(inner)
        if is_distinctive_core(company_core(inner)):
            out.add(key)
    return out


def is_distinctive_core(core):
    """True when a core name is specific enough to identify one company on its own."""
    if not core or core in AMBIGUOUS_CORES:
        return False
    tokens = core.split()
    if len(tokens) >= 2:
        return len(core.replace(" ", "")) >= 6 and not all(t in COMMON_BRAND_WORDS or len(t) <= 2 for t in tokens)
    return len(core) >= 5


def linkedin_slug(url):
    """'https://in.linkedin.com/in/John-Doe-12/?x' -> 'john-doe-12' (None if not a profile URL)."""
    text = clean_text(url).lower()
    match = re.search(r"linkedin\.com/in/([^/?#\s]+)", text)
    if not match:
        return None
    from urllib.parse import unquote
    return unquote(match.group(1)).strip("/").lower() or None


def name_tokens(name):
    text = ascii_fold(clean_text(name)).lower()
    text = re.sub(HONORIFICS, " ", text)
    text = re.sub(r"[^a-z ]", " ", text)
    return [t for t in text.split() if t]


def person_key(first, last=""):
    tokens = name_tokens(f"{first} {last}")
    return " ".join(tokens)


PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _looks_like_name(tokens):
    if not 1 <= len(tokens) <= 5:
        return False
    if all(t in DESIGNATION_WORDS for t in tokens):
        return False
    # A name made only of single letters ("R K") is not usable.
    return any(len(t) >= 3 for t in tokens)


def split_contacts(cell):
    """Split a free-text contact cell into [{'name', 'designation', 'phones', 'emails'}].

    Handles cells such as
      "Hitesh Patel (Head SCM)\\nRitesh Rajpali\\n(Sr. Manager)"
      "Mr. Jalal Sulaiman, MD"   "A Gupta / B Rao"   "Main Team :-\\n* D Shah - GM"
    """
    text = clean_text(cell)
    if not text:
        return []
    emails = EMAIL_RE.findall(text)
    text = EMAIL_RE.sub(" ", text)
    phones = [re.sub(r"\s+", " ", p).strip() for p in PHONE_RE.findall(text)]
    text = PHONE_RE.sub(" ", text)

    pieces = re.split(r"[\n;/|•*]+|\s&\s|\band\b|,\s*(?=(?:mr|mrs|ms|dr|shri)\b)", text, flags=re.I)
    people = []
    for piece in pieces:
        piece = piece.strip(" :-–,.\t")
        if not piece:
            continue
        bracketed = " ".join(re.findall(r"\((.*?)\)", piece)).strip()
        base = re.sub(r"\(.*?\)|\(.*$", " ", piece)
        # "Name, Designation", "Name - Designation" or "Name A, Name B, Name C"
        segments = [s for s in re.split(r",|\s[-–]\s|:-|:", base) if s.strip()]
        for seg in segments:
            tokens = name_tokens(seg)
            designation = ""
            # Strip trailing designation words glued to the name ("Amit Shah GM").
            while tokens and tokens[-1] in DESIGNATION_WORDS and len(tokens) > 1:
                designation = (tokens.pop() + " " + designation).strip()
            if _looks_like_name(tokens) and not any(t in DESIGNATION_WORDS for t in tokens):
                people.append({"name": " ".join(tokens), "designation": designation})
            elif people:
                # A segment or line that is only a designation belongs to the previous person.
                people[-1]["designation"] = (people[-1]["designation"] + " " + seg.strip()).strip()
        if bracketed and people:
            people[-1]["designation"] = (people[-1]["designation"] + " " + bracketed).strip()
    for p in people:
        p["phones"] = phones
        p["emails"] = emails
    return people
