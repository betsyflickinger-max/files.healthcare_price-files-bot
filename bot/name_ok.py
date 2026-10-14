import re
from rapidfuzz import fuzz
ABBR = {"hosp": "hospital", "ctr": "center", "cntr": "center", "med": "medical", "hlt": "health", "hlth": "health",
        "saint": "st", "mt": "mount", "univ": "university", "reg": "regional", "rehab": "rehabilitation",
        "rehabiliation": "rehabilitation", "mem": "memorial", "gen": "general", "cnty": "county", "spec": "specialty",
        "speciality": "specialty", "behav": "behavioral", "psych": "psychiatric", "comm": "community", "ctrs": "centers",
        "lukes": "luke", "marys": "mary", "josephs": "joseph", "johns": "john", "vincents": "vincent", "francis": "francis"}
STOPW = {"the", "of", "and", "at", "a", "an", "for", "inc", "llc", "lp", "ltd", "corp", "dba", "co", "ii", "iii", "iv",
         "hospital", "hospitals", "medical", "center", "centers", "health", "healthcare", "system", "systems", "campus",
         "an", "affiliate", "regional", "general", "community", "memorial", "facility", "services", "clinic", "llc"}
STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA "
             "RI SC SD TN TX UT VT VA WA WV WI WY DC PR".lower().split())
def toks(s):
    s = (s or "").lower().replace("&", " and ").replace("'", "").replace("’", "").replace("ʻ", "").replace(".", " ")
    out = []
    for t in re.sub(r"[^a-z0-9 ]", " ", s).split():
        out.append(ABBR.get(t, t))
    return out
def distinct(s):
    return [t for t in toks(s) if t not in STOPW and t not in STATES and len(t) > 1]
def name_ok(ours, theirs):
    """Every distinctive word of our name is in theirs (abbreviations expanded, small typos and a cut-off last word allowed)."""
    want, have = distinct(ours), toks(theirs)
    if not want:
        return False
    flat = "".join(have)
    for i, w in enumerate(want):
        if w in have or any(fuzz.ratio(w, h) >= 85 for h in have if len(w) >= 5):
            continue
        if len(w) >= 4 and w in flat:   # "neuro behavioral" vs "neurobehavioral", "careof"
            continue
        if i == len(want) - 1 and len(w) >= 3 and any(h.startswith(w) for h in have):
            continue
        return False
    return True
