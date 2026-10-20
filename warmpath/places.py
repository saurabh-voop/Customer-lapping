"""Clean city / state names so customers can be filtered by place.

Source sheets spell places many ways (Bombay/Mumbai, Bengaluru/Bangalore) and some tabs
lost every "na" ("Bhavgar" for Bhavnagar, "Tamil du" for Tamil Nadu), so names are mapped
through an alias table rather than trusted as written.
"""
import re

from .normalize import ascii_fold, clean_text

# canonical city -> state
CITY_STATE = {
    "Mumbai": "Maharashtra", "Navi Mumbai": "Maharashtra", "Thane": "Maharashtra", "Pune": "Maharashtra",
    "Nagpur": "Maharashtra", "Nashik": "Maharashtra", "Aurangabad": "Maharashtra", "Panvel": "Maharashtra",
    "Palghar": "Maharashtra", "Satara": "Maharashtra", "Solapur": "Maharashtra", "Jalgaon": "Maharashtra",
    "Kolhapur": "Maharashtra", "Ahmedabad": "Gujarat", "Surat": "Gujarat", "Vadodara": "Gujarat",
    "Rajkot": "Gujarat", "Bhavnagar": "Gujarat", "Jamnagar": "Gujarat", "Gandhinagar": "Gujarat",
    "Bharuch": "Gujarat", "Ankleshwar": "Gujarat", "Morbi": "Gujarat", "Kutch": "Gujarat", "Bhuj": "Gujarat",
    "Gandhidham": "Gujarat", "Anjar": "Gujarat", "Navsari": "Gujarat", "Valsad": "Gujarat", "Vapi": "Gujarat",
    "Mehsana": "Gujarat", "Banaskantha": "Gujarat", "Silvassa": "Dadra and Nagar Haveli",
    "Delhi": "Delhi", "Gurugram": "Haryana", "Faridabad": "Haryana", "Panipat": "Haryana", "Bahadurgarh": "Haryana",
    "Ambala": "Haryana", "Panchkula": "Haryana", "Noida": "Uttar Pradesh", "Ghaziabad": "Uttar Pradesh",
    "Greater Noida": "Uttar Pradesh", "Agra": "Uttar Pradesh", "Lucknow": "Uttar Pradesh", "Kanpur": "Uttar Pradesh",
    "Meerut": "Uttar Pradesh", "Mathura": "Uttar Pradesh", "Hyderabad": "Telangana", "Secunderabad": "Telangana",
    "Rangareddy": "Telangana", "Bangalore": "Karnataka", "Mangalore": "Karnataka", "Belgaum": "Karnataka",
    "Bellary": "Karnataka", "Hosur": "Tamil Nadu", "Chennai": "Tamil Nadu", "Coimbatore": "Tamil Nadu",
    "Tiruvallur": "Tamil Nadu", "Tuticorin": "Tamil Nadu", "Kanchipuram": "Tamil Nadu", "Tiruppur": "Tamil Nadu",
    "Erode": "Tamil Nadu", "Madurai": "Tamil Nadu", "Tirunelveli": "Tamil Nadu", "Kolkata": "West Bengal",
    "Siliguri": "West Bengal", "Jalpaiguri": "West Bengal", "Darjeeling": "West Bengal",
    "North 24 Parganas": "West Bengal", "Jaipur": "Rajasthan", "Kota": "Rajasthan", "Udaipur": "Rajasthan",
    "Jodhpur": "Rajasthan", "Ajmer": "Rajasthan", "Bhopal": "Madhya Pradesh", "Indore": "Madhya Pradesh",
    "Jabalpur": "Madhya Pradesh", "Pithampur": "Madhya Pradesh", "Rewa": "Madhya Pradesh",
    "Raipur": "Chhattisgarh", "Bhilai": "Chhattisgarh", "Durg": "Chhattisgarh", "Bilaspur": "Chhattisgarh",
    "Ludhiana": "Punjab", "Jalandhar": "Punjab", "Mohali": "Punjab", "Patiala": "Punjab", "Chandigarh": "Chandigarh",
    "Ernakulam": "Kerala", "Kochi": "Kerala", "Thrissur": "Kerala", "Thiruvananthapuram": "Kerala",
    "Visakhapatnam": "Andhra Pradesh", "Vijayawada": "Andhra Pradesh", "Rajahmundry": "Andhra Pradesh",
    "Nellore": "Andhra Pradesh", "Guntur": "Andhra Pradesh", "Ranchi": "Jharkhand", "Jamshedpur": "Jharkhand",
    "Rourkela": "Odisha", "Bhubaneswar": "Odisha", "Guwahati": "Assam", "Nalbari": "Assam", "Patna": "Bihar",
    "Goa": "Goa", "Dehradun": "Uttarakhand",
}
# raw spelling (lower case, punctuation removed) -> canonical city
CITY_ALIASES = {
    "bombay": "Mumbai", "andheri": "Mumbai", "vi mumbai": "Navi Mumbai", "navi mumbai": "Navi Mumbai",
    "new delhi": "Delhi", "delhi ncr": "Delhi", "ncr": "Delhi", "gurgaon": "Gurugram", "gurugaon": "Gurugram",
    "bengaluru": "Bangalore", "bangaluru": "Bangalore", "cheni": "Chennai", "madras": "Chennai",
    "bhavgar": "Bhavnagar", "ludhia": "Ludhiana", "erkulam": "Ernakulam", "cochin": "Kochi", "shik": "Nashik",
    "nasik": "Nashik", "gpur": "Nagpur", "visakhapatm": "Visakhapatnam", "vizag": "Visakhapatnam",
    "jamgar": "Jamnagar", "gandhigar": "Gandhinagar", "vadodra": "Vadodara", "vodadara": "Vadodara",
    "baroda": "Vadodara", "hydbad": "Hyderabad", "hyd": "Hyderabad", "sikandrabad": "Secunderabad",
    "k v rangareddy": "Rangareddy", "rangareddy": "Rangareddy", "rajhmundry": "Rajahmundry",
    "mahesa": "Mehsana", "mahesana": "Mehsana", "baskantha": "Banaskantha", "kachchh": "Kutch", "kachh": "Kutch",
    "gautam buddha gar": "Greater Noida", "gautam buddha nagar": "Greater Noida", "north 24 pargas": "North 24 Parganas",
    "lbari": "Nalbari", "thiruvanthapuram": "Thiruvananthapuram", "trivandrum": "Thiruvananthapuram",
    "valad": "Valsad", "calcutta": "Kolkata", "poona": "Pune", "trichy": "Tiruchirappalli",
}
STATE_ALIASES = {
    "tamil du": "Tamil Nadu", "tamildu": "Tamil Nadu", "tamilnadu": "Tamil Nadu", "tn": "Tamil Nadu",
    "telanga": "Telangana", "kartaka": "Karnataka", "harya": "Haryana", "kerela": "Kerala",
    "chattisgarh": "Chhattisgarh", "andhra": "Andhra Pradesh", "ap": "Andhra Pradesh", "mp": "Madhya Pradesh",
    "up": "Uttar Pradesh", "new delhi": "Delhi", "orissa": "Odisha", "pondicherry": "Puducherry",
    "maharastra": "Maharashtra",
}
STATES = {s.lower(): s for s in set(CITY_STATE.values()) | {
    "Maharashtra", "Gujarat", "Delhi", "Uttar Pradesh", "West Bengal", "Tamil Nadu", "Telangana", "Haryana",
    "Karnataka", "Rajasthan", "Punjab", "Kerala", "Andhra Pradesh", "Madhya Pradesh", "Chhattisgarh", "Odisha",
    "Assam", "Goa", "Bihar", "Jharkhand", "Uttarakhand", "Himachal Pradesh", "Puducherry", "Jammu and Kashmir"}}
_CITY_LOWER = {c.lower(): c for c in CITY_STATE}
NOT_A_PLACE = {"", "nil", "na", "export", "location", "inital", "initial", "india", "-", "tbd"}


def _key(text):
    text = ascii_fold(clean_text(text)).lower()
    text = re.sub(r"\(.*?\)", " ", text)
    text = re.sub(r"[^a-z0-9 ]", " ", text.replace("'", ""))
    return re.sub(r"\s+", " ", text).strip()


def _city(key):
    if key in CITY_ALIASES:
        return CITY_ALIASES[key]
    return _CITY_LOWER.get(key)


def _state(key):
    return STATE_ALIASES.get(key) or STATES.get(key)


def clean_place(location, state="", country=""):
    """-> (city, state, country). Unknown parts come back as ''."""
    city = st = ""
    raw = clean_text(location)
    pieces = [raw] + re.split(r"[,/;\n]| - ", raw)
    for piece in pieces:
        key = _key(piece)
        if key in NOT_A_PLACE:
            continue
        city = _city(key) or ""
        if not city:
            # "Surat Gujarat", "Pune viman nagar": try each word and word pair
            words = key.split()
            for n in (3, 2, 1):
                for i in range(len(words) - n + 1):
                    city = _city(" ".join(words[i:i + n])) or ""
                    if city:
                        break
                if city:
                    break
        if not city and not st:
            st = _state(key) or ""
        if city:
            break
    if not city and not st:
        # Keep an unlisted town as written ("Moradabad", "Udupi"); repair "...gar" -> "...nagar".
        key = _key(pieces[0])
        words = key.split()
        if key not in NOT_A_PLACE and 1 <= len(words) <= 3 and all(w.isalpha() for w in words):
            if words[-1].endswith("gar") and not words[-1].endswith("nagar") and len(words[-1]) > 5:
                words[-1] = words[-1][:-3] + "nagar"
            city = " ".join(w.capitalize() for w in words)
    st = _state(_key(state)) or st or (CITY_STATE.get(city, "") if city else "")
    if city and not st:
        st = CITY_STATE.get(city, "")
    ctry = clean_text(country).title()
    if not ctry and (city or st):
        ctry = "India"
    return city, st, ctry
