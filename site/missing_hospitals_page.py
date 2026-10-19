"""Price File Watch, hospitals list (/price-file-watch/hospitals/): every hospital where we couldn't find a usable
price file, by state (Texas first), with what we tried and when, and a "send us the link" button. Oct 19, 2026 (Betsy).

  python site/missing_hospitals_page.py reports/watch/missing-hospitals-<date>.csv OUT_DIR   -> OUT_DIR/index.html

Input: bot/missing_export.py (the daily run's status + the web search log). Left off the list, and only counted:
federal hospitals (the rule doesn't cover them), hospitals reported closed, and hospitals whose possible file is still
being checked. Wording says what we could and couldn't find, never that a hospital broke the rule.
"""
import csv
import html
import sys
import urllib.parse
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hospital_profiles as hp  # noqa: E402  (page shell: same look and nav)

E = html.escape
NAMES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
         "CT": "Connecticut", "DE": "Delaware", "DC": "Washington, DC", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
         "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
         "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
         "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
         "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
         "OR": "Oregon", "PA": "Pennsylvania", "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina",
         "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
         "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "GU": "Guam", "VI": "U.S. Virgin Islands"}
TYPE = {"Acute Care Hospitals": "Hospital", "Critical Access Hospitals": "Rural (critical access) hospital",
        "Psychiatric": "Psychiatric hospital", "Inpatient Rehabilitation": "Rehabilitation hospital",
        "Long-term": "Long-term care hospital", "Childrens": "Children's hospital", "Rural Emergency Hospital": "Rural emergency hospital"}
LABEL = {"no price file found": "No price file found", "link broken": "Posted link doesn't work",
         "not a price file": "Link isn't a price file", "wrong hospital's file": "Link is another hospital's file"}
SMALL = {"of", "and", "the", "at", "for", "in", "on", "de", "la", "del"}
KEEP = {"LLC", "LTC", "PHS", "UMMC", "UAB", "UNC", "UCSF", "UCLA", "UC", "VA", "MD", "HCA", "CHI", "SSM", "OSF", "II", "III", "IV"}


def title(s):
    out = []
    for i, w in enumerate(s.split()):
        out.append(w if w in KEEP else (w.lower() if i and w.lower() in SMALL else w.capitalize()))
    return " ".join(out).replace("'S ", "'s ")


def day(iso):
    try:
        return date.fromisoformat(iso[:10]).strftime("%B %-d, %Y")
    except ValueError:
        return ""


def tried(r):
    n = r.get("times_searched") or ""
    when = day(r.get("searched_at", "")) or day(r.get("last_checked", ""))
    checked = day(r.get("last_checked", ""))
    if r["status"] == "no price file found":
        s = "Checked the hospital's required index file (cms-hpt.txt) and its website"
        if n and n != "0":
            s += f", and searched the web {'once' if n == '1' else n + ' times'}" + (f", most recently {when}" if when else "")
        return s + "."
    if r["status"] == "link broken":
        return f"The link the hospital posted stopped working" + (f" (last tried {checked})" if checked else "") + "."
    if r["status"] == "not a price file":
        return "The hospital's link opens a web page or document, not a machine-readable price file" + (f" (checked {checked})" if checked else "") + "."
    return "The file at the hospital's link names another hospital's address" + (f" (checked {checked})" if checked else "") + "."


def mailto(r):
    q = urllib.parse.urlencode({"subject": f"Price file for {title(r['name'])} ({r['state']}, CCN {r['ccn']})",
                                "body": "The price file is posted here: "}, quote_via=urllib.parse.quote)
    return f"mailto:corrections@files.healthcare?{q}"


CSS = """
.mh h1{font:600 clamp(30px,6vw,46px)/1.08 var(--display);margin:8px 0 10px}
.mh .lede{max-width:68ch;font-size:17px}
.mh .count{display:flex;flex-wrap:wrap;gap:22px 34px;margin:22px 0 8px}
.mh .count b{display:block;font:700 30px/1 var(--type);color:var(--brick)}
.mh .count span{font:14px/1.4 var(--body);color:var(--ink-2);display:block;max-width:26ch}
.mh .pick{margin:26px 0 6px;display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.mh .pick select{font:600 16px var(--body);padding:8px 10px;border:1.5px solid var(--ink);border-radius:2px;background:var(--paper);color:var(--ink);max-width:100%}
.mh section{border-top:2px solid var(--ink);margin-top:30px;padding-top:4px}
.mh h2{font:600 26px/1.15 var(--display);margin:14px 0 4px}
.mh .row{display:grid;grid-template-columns:1fr auto;gap:6px 18px;padding:14px 0;border-bottom:1px solid var(--rule)}
.mh .row h3{font:600 17px/1.3 var(--body);margin:0}
.mh .who{font-size:14px;color:var(--ink-2)}
.mh .why{font-size:14px;margin:4px 0 0;max-width:70ch}
.mh .stamp{font:700 12px var(--type);text-transform:uppercase;letter-spacing:.04em;color:var(--brick);border:1.5px solid var(--brick);padding:2px 6px;border-radius:2px;white-space:nowrap;align-self:start}
.mh .send{grid-column:1/-1;font-size:14px}
.mh .mh-note{font-size:14px;color:var(--ink-2);max-width:72ch}
.mh [hidden]{display:none}
@media (max-width:560px){.mh .row{grid-template-columns:1fr}.mh .stamp{justify-self:start}}
"""


def build(rows, today):
    listed, held, federal, closed, reh = [], 0, 0, 0, 0
    for r in rows:
        res = r.get("search_result", "")
        if r.get("type") == "Rural Emergency Hospital":
            reh += 1      # whether the rule covers rural emergency hospitals isn't confirmed yet: counted, not listed
        elif res == "exempt (federal)":
            federal += 1
        elif res == "reported closed":
            closed += 1
        elif r["status"] == "no price file found" and res in ("held", "found"):
            held += 1     # a possible file is being checked: not listed until it's ruled out
        else:
            listed.append(r)
    by = defaultdict(list)
    for r in listed:
        by[r["state"]].append(r)
    states = sorted(by, key=lambda s: (s != "TX", NAMES.get(s, s)))
    opts = "".join(f'<option value="{s}">{E(NAMES.get(s, s))} ({len(by[s])})</option>' for s in states)
    secs = []
    for s in states:
        items = []
        for r in sorted(by[s], key=lambda r: (r["city"], r["name"])):
            items.append(
                f'<div class="row"><div><h3>{E(title(r["name"]))}</h3>'
                f'<div class="who">{E(title(r["city"]))} · {E(TYPE.get(r["type"], r["type"] or "Hospital"))} · CMS number {E(r["ccn"])}</div>'
                f'<p class="why">{E(tried(r))}</p></div>'
                f'<span class="stamp">{E(LABEL.get(r["status"], r["status"]))}</span>'
                f'<div class="send">Know where its file is? <a href="{E(mailto(r))}">Send us the link</a></div></div>')
        secs.append(f'<section data-st="{s}"{"" if s == "TX" else " hidden"}><h2>{E(NAMES.get(s, s))}</h2>'
                    f'<p class="mh-note">{len(by[s])} hospital{"s" if len(by[s]) != 1 else ""}</p>{"".join(items)}</section>')
    url = "https://files.healthcare/price-file-watch/hospitals/"
    head = hp.shell("Hospitals without a usable price file", "Every U.S. hospital where we couldn't find a usable "
                    "machine-readable price file, by state, with what we tried and when.", url, current_hospitals=False)
    head = head.replace("</style>\n</head>", CSS + "</style>\n</head>", 1) if CSS not in head else head
    return head + f"""
<main class="mh">
<header>
  <div class="eyebrow"><a href="/price-file-watch/">Price File Watch</a> · Hospitals, every state</div>
  <h1>Hospitals where we couldn't find a usable price file</h1>
  <p class="lede">Federal rules (45 CFR 180) require every hospital to post one machine-readable file of its standard charges and to list it in a file called cms-hpt.txt on its website. Most do. For the hospitals below, we couldn't find one we could use. Each entry says what we tried and when. If a file exists somewhere we didn't look, tell us and we'll re-check and update this page.</p>
  <div class="count">
    <div><b>{len(listed):,}</b><span>hospitals listed below</span></div>
    <div><b>{held:,}</b><span>possible files still being checked (not listed)</span></div>
    <div><b>{federal:,}</b><span>federal hospitals (VA, Indian Health Service); the rule doesn't cover them</span></div>
    <div><b>{closed:,}</b><span>reported closed (not listed)</span></div>
    <div><b>{reh:,}</b><span>rural emergency hospitals (not listed while we confirm whether the rule covers them)</span></div>
  </div>
</header>
<div class="pick"><label for="st"><b>State</b></label><select id="st">{opts}</select></div>
{"".join(secs)}
<p class="mh-note" style="margin-top:28px">How we checked: a bot reads each hospital's cms-hpt.txt and the file it lists about once a week. When there's no working file, it searches the hospital's website, web archives and the wider web, and checks that any file it finds is this hospital's own (its name or street address). Hospitals come from Medicare's hospital lists. Updated {day(today.isoformat())}. <a href="/price-file-watch/">Back to the Price File Watch</a> · <a href="/corrections/">Corrections</a></p>
</main>
</div>
<script>
(function(){{var s=document.getElementById('st');function show(v){{document.querySelectorAll('.mh section[data-st]').forEach(function(x){{x.hidden=x.getAttribute('data-st')!==v}});try{{history.replaceState(null,'','#'+v)}}catch(e){{}}}}
var h=(location.hash||'').slice(1).toUpperCase();if(h&&s.querySelector('option[value="'+h+'"]')){{s.value=h}}show(s.value);s.addEventListener('change',function(){{show(s.value)}});}})();
</script>
</body></html>
""", len(listed)


def main(src, out):
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    page, n = build(rows, date.today())
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote {out}/index.html: {n} hospitals listed")
    return n


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
