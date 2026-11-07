"""Everyday words -> billing codes for the Price Finder search (Nov 7, 2026; Betsy: "transabdominal myomectomy" found
nothing, so she had to Google CPT 58140/58146).

Reads reference/care_items/crosswalk_codes.csv (every care item's CPT and MS-DRG codes) plus the plain words people
use (WORDS below), and writes them into site/assets/pf-table.js between /*ALIASES:START*/ and /*ALIASES:END*/.
Run after the care items change:  python site/search_aliases.py
"""
import csv
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JS = os.path.join(HERE, 'assets', 'pf-table.js')
SRC = os.path.join(ROOT, 'reference', 'care_items', 'crosswalk_codes.csv')
KEEP_ROLE = re.compile(r'^(doctor:|hospital stay:|facility or lab: same-day)')
# the words people actually type, beyond the care item's own name (medical and everyday)
WORDS = {
    'carpal-tunnel': 'wrist hand numbness tingling', 'cataract': 'eye lens cloudy vision',
    'colonoscopy': 'colon polyp screening', 'gallbladder': 'cholecystectomy gallstones',
    'knee-scope': 'meniscus meniscectomy arthroscopy torn',
    'afib-ablation': 'atrial fibrillation rhythm', 'anti-reflux-surgery-nissen': 'reflux gerd fundoplication hiatal heartburn',
    'aortic-valve-replacement-catheter-tavr': 'valve tavi transcatheter', 'aortic-valve-replacement-open': 'valve avr',
    'appendectomy-laparoscopic': 'appendix appendicitis', 'c-section': 'cesarean caesarean birth baby',
    'carotid-endarterectomy': 'carotid neck artery stroke', 'colon-resection-laparoscopic': 'colectomy bowel resection',
    'coronary-stent-pci': 'stent angioplasty blocked artery', 'defibrillator-icd-implant': 'defibrillator aicd icd',
    'ectopic-pregnancy-surgery-laparoscopic': 'tubal salpingectomy', 'fibroid-removal-myomectomy':
        'myomectomy fibroid fibroids uterine leiomyoma laparotomy',
    'gastric-bypass': 'bariatric roux', 'gastric-sleeve': 'bariatric gastrectomy', 'heart-bypass-cabg': 'cabg coronary bypass',
    'hip-fracture-repair-nail': 'broken hip femur fracture', 'hip-replacement': 'arthroplasty tha',
    'hysterectomy-abdominal': 'uterus removal', 'hysterectomy-laparoscopic': 'uterus removal',
    'inguinal-hernia-repair-laparoscopic': 'groin hernia', 'kidney-removal-for-cancer-laparoscopic': 'nephrectomy',
    'kidney-stone-removal-ureteroscopy': 'kidney stone lithotripsy ureteroscopy', 'knee-replacement': 'arthroplasty tka',
    'low-back-disc-surgery-laminotomy-discectomy': 'herniated disc slipped sciatica discectomy laminotomy',
    'low-back-fusion-one-level': 'spinal fusion tlif lumbar', 'lung-lobectomy-vats': 'lobectomy vats',
    'mastectomy': 'breast removal', 'neck-fusion-acdf-one-level': 'acdf cervical fusion', 'pacemaker-implant': 'pacemaker',
    'prostate-removal-robotic': 'prostatectomy', 'prostate-trimming-turp': 'turp bph enlarged prostate',
    'shoulder-replacement': 'arthroplasty', 'thyroid-removal': 'thyroidectomy', 'vaginal-delivery': 'birth baby labor childbirth',
    'ventral-belly-hernia-repair-with-mesh': 'incisional abdominal hernia',
}


def build():
    items = {}
    for r in csv.DictReader(open(SRC, encoding='utf-8')):
        if r['code_system'] not in ('CPT', 'MS-DRG') or not KEEP_ROLE.match(r['role']) or not r['code']:
            continue
        it = items.setdefault(r['item_id'], [r['plain_name'], [], []])
        code = r['code'].lstrip('0') if r['code_system'] == 'MS-DRG' else r['code']   # the page keys DRGs without zeros
        if code not in it[2]:
            it[2].append(code)
    out = []
    for iid, (name, _, codes) in sorted(items.items()):
        words = sorted(set(re.findall(r'[a-z0-9]+', (name + ' ' + iid.replace('-', ' ') + ' ' + WORDS.get(iid, '')).lower())))
        out.append([name, ' '.join(words), codes])
    return out


def anes():
    """procedure code -> the care item's main anesthesia code, for the Price Finder's anesthesia link (Nov 7, 2026)."""
    rows = list(csv.DictReader(open(SRC, encoding='utf-8')))
    main_anes = {r['item_id']: r['code'] for r in rows if r['role'] == 'anesthesia: main code' and r['code']}
    out = {}
    for r in rows:
        if r['item_id'] in main_anes and r['code_system'] in ('CPT', 'MS-DRG') and KEEP_ROLE.match(r['role']) and r['code']:
            out.setdefault(r['code'].lstrip('0') if r['code_system'] == 'MS-DRG' else r['code'], main_anes[r['item_id']])
    return out


def main():
    s = open(JS, encoding='utf-8').read()
    a, b = s.index('/*ANES:START*/'), s.index('/*ANES:END*/')
    s = s[:a] + '/*ANES:START*/' + json.dumps(anes(), separators=(',', ':')) + s[b:]
    a, b = s.index('/*ALIASES:START*/'), s.index('/*ALIASES:END*/')
    data = json.dumps(build(), separators=(',', ':'))
    s = s[:a] + '/*ALIASES:START*/' + data + s[b:]
    open(JS, 'w', encoding='utf-8').write(s)
    print(f'search aliases: {len(json.loads(data))} care items written into {os.path.relpath(JS, ROOT)}')


if __name__ == '__main__':
    main()
