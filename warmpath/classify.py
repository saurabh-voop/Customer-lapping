"""Sector and seniority tagging for LinkedIn connections (same buckets as Atul's sheet, extended)."""
import re

TIERS = [
    ("1 - Chairman / MD", r"\b(chairman|chairperson|managing director|\bmd\b|cmd)\b"),
    ("2 - CEO / Founder / Owner / President / ED",
     r"\b(ceo|chief executive|founder|co-founder|cofounder|owner|proprietor|president|executive director|\bed\b|promoter)\b"),
    ("3 - Director / Partner", r"\b(director|partner|principal)\b"),
    ("4 - CXO / VP / GM / Head",
     r"\b(cfo|coo|cto|cio|cmo|chro|cpo|chief|vice president|\bvp\b|\bavp\b|\bsvp\b|\bevp\b|general manager|\bgm\b|\bdgm\b|\bagm\b|head|hod)\b"),
    ("5 - Manager / Lead", r"\b(manager|lead|in-?charge|controller|superintendent)\b"),
]
OTHER_TIER = "6 - Engineer / Other"

SECTORS = [
    ("Gensets / Engines", r"genset|generator|diesel|cummins|kirloskar|engine|perkins|mtu|caterpillar|\bdg\b"),
    ("Transformers / Electrical / Cables / Panels",
     r"transformer|switchgear|panel|cable|electrical|substation|\bhv\b|\blt\b|schneider|siemens|abb|hitachi energy|l&t electrical|havells|polycab"),
    ("Solar / Renewables / BESS", r"solar|renewable|\bbess\b|battery|storage|wind|green energy|hydrogen|\bev\b|clean energy|photovoltaic|\bpv\b"),
    ("Energy & Power (general)", r"power|energy|utility|electricity|discom|grid|thermal|hydro|nuclear|oil|gas|petroleum|refinery"),
    ("Construction / Real Estate / Infra",
     r"construct|infra|epc|builder|developer|realty|real estate|properties|cement|road|highway|metro|railway|bridge|tunnel|port|airport|buildcon"),
    ("Water / Wastewater", r"water|wastewater|sewage|desalination|wabag|effluent"),
    ("Pumps / Compressors / Mechanical Engg", r"pump|compressor|valve|mechanical|hvac|boiler|thermax|turbine"),
    ("Automation / Instrumentation / Industrial Tech", r"automation|instrument|scada|plc|robot|control systems|iot"),
    ("Chemicals / Materials / Metals / Manufacturing",
     r"chemical|steel|metal|alumin|copper|plastic|polymer|textile|paper|glass|manufactur|mining|minerals|fertili"),
    ("Logistics / Shipping / Marine / Trading", r"logistic|shipping|marine|freight|cargo|trading|import|export|supply chain"),
    ("Finance / PE / VC / Advisory / Consulting",
     r"bank|capital|invest|fund|equity|venture|finance|financial|advisory|consult|audit|deloitte|kpmg|\bey\b|pwc|mckinsey|bcg|bain|securities|asset management|insurance|wealth"),
    ("IT / Software / Digital", r"software|\bit\b|digital|technolog|tech\b|cloud|data|\bai\b|google|microsoft|amazon|apple|intel|meta|infosys|tcs|wipro|accenture"),
    ("Healthcare / Pharma / Life Sciences", r"health|hospital|pharma|medical|life science|biotech|clinic"),
    ("Automotive / Mobility", r"automotive|auto\b|motors|vehicle|mobility|tyre"),
    ("Hospitality / Food / Travel / Lifestyle", r"hotel|hospitality|food|restaurant|travel|tourism|beverage|fashion|retail"),
    ("Media / Marketing / Events", r"media|marketing|advertis|event|pr\b|publishing|news"),
    ("Chambers / Associations / Education / Govt",
     r"chamber|association|council|federation|university|college|institute|school|government|ministry|govt|embassy|consulate"),
]
OTHER_SECTOR = "Diversified / Group / Unclear"

# Functions that buy, specify or influence DG sets / panels / transformers.
BUYER_FUNCTION_RE = re.compile(
    r"purchase|procurement|sourcing|scm|supply chain|projects?|electrical|mep|tender|"
    r"contracts|commercial|plant head|operations|maintenance|engineering|design|epc|utilities",
    re.I,
)


def tier_of(position):
    text = (position or "").lower()
    for label, pattern in TIERS:
        if re.search(pattern, text):
            return label
    return OTHER_TIER


def tier_rank(tier_label):
    return int(tier_label[0]) if tier_label and tier_label[0].isdigit() else 6


def sector_of(company, position=""):
    text = f"{company or ''} | {position or ''}".lower()
    for label, pattern in SECTORS:
        if re.search(pattern, text):
            return label
    return OTHER_SECTOR


def is_buyer_function(position):
    return bool(BUYER_FUNCTION_RE.search(position or ""))
