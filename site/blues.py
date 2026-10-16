"""Which Blue Cross Blue Shield company a "Blue Cross" price belongs to (Oct 15, 2026).

Before: every Blue Cross price, in every state, was labeled BCBSTX (Blue Cross and Blue Shield of Texas). Georgia's and
Colorado's Anthem networks, BCBS of Alabama, Mississippi and Oklahoma all showed as BCBSTX on the state pages.

Each state has its own Blue plan (some have two). A hospital file that just says "BCBS" means that state's own Blue plan:
out-of-state Blue members are paid at the local plan's contract (the BlueCard program). Where a state has more than one Blue
plan and the file doesn't say which, the label is the plain "Blue Cross Blue Shield": we don't guess which one.

  home(area)            the label for an unnamed Blue Cross price in that area (a state slug or a Texas metro)
  hospital_label(p, a)  hospital-file payer name p, in area a -> the Blue label, or "" if p isn't a Blue plan
  SQL_SHORT             insurer-file rule (DuckDB CASE fragment), keyed on the network's own label from the network list
"""

GENERIC = "Blue Cross Blue Shield"

# state slug -> label for that state's Blue plan; None = more than one Blue plan covers the state
HOME = {
    "alabama": "BCBS Alabama", "alaska": "Premera", "arizona": "BCBS Arizona", "arkansas": "Arkansas BCBS",
    "california": None, "colorado": "Anthem Colorado", "connecticut": "Anthem Connecticut", "delaware": "Highmark Delaware",
    "district-of-columbia": "CareFirst", "florida": "Florida Blue", "georgia": "Anthem Georgia", "hawaii": "HMSA",
    "idaho": None, "illinois": "BCBS Illinois", "indiana": "Anthem Indiana", "iowa": "Wellmark", "kansas": None,
    "kentucky": "Anthem Kentucky", "louisiana": "BCBS Louisiana", "maine": "Anthem Maine", "maryland": "CareFirst",
    "massachusetts": "BCBS Massachusetts", "michigan": "BCBS Michigan", "minnesota": "BCBS Minnesota",
    "mississippi": "BCBS Mississippi", "missouri": None, "montana": "BCBS Montana", "nebraska": "BCBS Nebraska",
    "nevada": "Anthem Nevada", "new-hampshire": "Anthem New Hampshire", "new-jersey": "Horizon BCBS", "new-mexico": "BCBS New Mexico",
    "new-york": None, "north-carolina": "Blue Cross NC", "north-dakota": "BCBS North Dakota", "ohio": "Anthem Ohio",
    "oklahoma": "BCBSOK", "oregon": "Regence Oregon", "pennsylvania": None, "rhode-island": "BCBS Rhode Island",
    "south-carolina": "BCBS South Carolina", "south-dakota": "Wellmark", "tennessee": "BlueCross BlueShield of Tennessee",
    "texas": "BCBSTX", "utah": "Regence Utah", "vermont": "BCBS Vermont", "virginia": None, "washington": None,
    "west-virginia": "Highmark West Virginia", "wisconsin": "Anthem Wisconsin", "wyoming": "BCBS Wyoming",
}

# words in a payer name that name one Blue plan outright, whatever state the hospital is in (checked in this order)
NAMED = [
    (("blue cross and blue shield of texas", "bcbs of texas", "bcbs texas", "bcbstx", "blue cross blue shield of texas"), "BCBSTX"),
    (("oklahoma", "bcbsok"), "BCBSOK"),
    (("tennessee", "bcbst"), "BlueCross BlueShield of Tennessee"),
    (("alabama",), "BCBS Alabama"), (("mississippi",), "BCBS Mississippi"),
    (("kansas city", "blue kc", "bluekc"), "Blue KC"),
    (("illinois",), "BCBS Illinois"), (("louisiana",), "BCBS Louisiana"), (("arkansas",), "Arkansas BCBS"),
    (("florida blue",), "Florida Blue"), (("highmark",), "Highmark"), (("carefirst",), "CareFirst"),
    (("regence",), "Regence"), (("premera",), "Premera"), (("wellmark",), "Wellmark"), (("horizon",), "Horizon BCBS"),
]
BLUE_WORDS = ("blue cross", "bluecross", "bcbs", "blue shield", "blueshield", "anthem", "blue kc", "bluekc")
TX_METROS = {"dfw", "houston", "austin", "san-antonio", "el-paso", "rest", "small-towns"}


def home(area):
    """Label for an unnamed Blue Cross price in an area. Texas metro pages are Texas."""
    a = (area or "texas").lower()
    if a in HOME:
        return HOME[a] or GENERIC
    return "BCBSTX"   # every other area slug is a Texas metro page (abilene, waco, ...)


def hospital_label(payer, area):
    p = (payer or "").lower()
    if not any(w in p for w in BLUE_WORDS):
        return ""
    for words, label in NAMED:
        if any(w in p for w in words):
            return label
    if "anthem" in p:   # Anthem without a state: the area's Anthem plan, if it has one
        h = home(area)
        return h if h.startswith("Anthem") else "Anthem"
    return home(area)


# Insurer files: the network list (insurers/networks*.csv) already says which company each file belongs to, and that name
# is carried on every row as file_label. Anthem's Colorado and Georgia rates, and BCBS Alabama's and Mississippi's, are read
# from BlueCard files that Blue Cross and Blue Shield of Oklahoma hosts, so the reporting entity can't be used for these.
SQL_SHORT = """when file_label ilike 'BCBSTX%' then 'BCBSTX'
 when file_label ilike 'BCBSOK%' then 'BCBSOK'
 when file_label ilike 'Anthem Colorado%' then 'Anthem Colorado' when file_label ilike 'Anthem Georgia%' then 'Anthem Georgia'
 when file_label ilike 'BCBS Alabama%' then 'BCBS Alabama' when file_label ilike 'BCBS Mississippi%' then 'BCBS Mississippi'
 when file_label ilike 'Blue KC%' then 'Blue KC'
 when reporting_entity_name ilike '%blue cross%of texas%' then 'BCBSTX'
 when reporting_entity_name ilike '%blue cross%' then reporting_entity_name"""
