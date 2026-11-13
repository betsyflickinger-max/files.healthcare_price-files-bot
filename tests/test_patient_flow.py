"""analysis/patient_flow/build.py on a tiny made-up country (Nov 13, 2026; Research Desk v1, story 2.2)."""
import csv, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis", "patient_flow"))
import build as pf

# Two Texas metros: Big (48001) and Small (48003), whose residents mostly use Big. Rural 48005 uses Big most.
# Rural 48007 has too few stays. Rural Oklahoma county 40001 uses Big (across the state line).
METRO = {'48001': '10000', '48003': '20000'}
MNAME = {'10000': 'Big, TX', '20000': 'Small, TX'}
ZC = {'75001': '48001', '75003': '48003', '75005': '48005', '75007': '48007', '73001': '40001', '75999': '48001'}
HZ = {'450001': '75999', '450002': '75003', '451301': '75005'}   # 450001 sits on a PO-box ZIP placed in Big
ROWS = [  # patient ZIP, hospital, stays
    ('75001', '450001', 900), ('75001', '450002', 20),
    ('75003', '450001', 300), ('75003', '450002', 100),
    ('75005', '450001', 60), ('75005', '451301', 40),
    ('75007', '450001', 12),
    ('73001', '450001', 80),
    ('75001', '455001', 999),     # a nursing home: not counted
    ('75001', '450002', '*'),     # hidden by CMS
]


def run(tmp_path):
    src = tmp_path / 'src'; src.mkdir()
    with open(src / 'hsaf.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['MEDICARE_PROV_NUM', 'ZIP_CD_OF_RESIDENCE', 'TOTAL_CASES'])
        for z, h, n in ROWS:
            w.writerow([h, z, n])
    return pf.build(str(src), str(tmp_path / 'out'), metro=METRO, mname=MNAME, zc=ZC, cname={}, hosp_zip=HZ), tmp_path / 'out'


def rows(out, name):
    return {r.get('fips') or r['area_id']: r for r in json.load(open(out / (name + '.json')))['rows']}


def test_rule(tmp_path):
    s, out = run(tmp_path)
    c = rows(out, 'counties')
    assert c['48005']['area_id'] == 'M10000'                                  # rural county joins the metro it uses most
    assert c['40001']['area_id'] == 'M10000' and 'across the state line' in c['40001']['note']
    assert c['48007']['area_id'] == 'RTX' and c['48007']['note'].startswith('under 50')
    assert c['48003']['area_id'] == 'M10000' and 'mostly use Big' in c['48003']['note']   # small metro folds in
    assert s['small_metros_merged'] == 1 and s['hidden_cells'] == 1
    assert s['stays_counted'] == 900 + 20 + 300 + 100 + 60 + 40 + 12 + 80    # nursing home left out


def test_sources_and_dates(tmp_path):
    _, out = run(tmp_path)
    for name in ('areas', 'counties', 'summary'):
        d = json.load(open(out / (name + '.json')))
        assert d['built_at'] and d['sources'] and d['rule'] and d['leaves_out']
    assert open(out / 'areas.csv').readline().startswith('# CMS Hospital Service Area File')


def test_hospital_kinds():
    assert pf.is_hospital('450001') and pf.is_hospital('451301') and pf.is_hospital('453301')
    assert not pf.is_hospital('455001') and not pf.is_hospital('45M001') and not pf.is_hospital('4500')


def test_po_box_zip_from_geonames(tmp_path):
    z = tmp_path / 'z.txt'
    z.write_text('GEOID_ZCTA5_20|GEOID_COUNTY_20|NAMELSAD_COUNTY_20|AREALAND_PART\n'
                 '75001|48001|Big County|10\n75001|48003|Small County|90\n', encoding='utf-8')
    g = tmp_path / 'g.txt'
    g.write_text('US\t75999\tBig\tTexas\tTX\tBig\t001\t\t\t0\t0\t4\n', encoding='utf-8')
    zc, names = pf.read_zip_county(str(z), geonames=str(g))
    assert zc['75001'] == '48003'          # county with most land wins
    assert zc['75999'] == '48001'          # PO-box ZIP placed from GeoNames
    assert names['48001'] == 'Big County'
