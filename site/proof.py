"""Proof a provider does a procedure, for the price pages (card #2, Betsy OK'd Oct 30-31, 2026).

Reads the Texas proof table built by utilization/build_evidence.py (storage data/utilization/<year>/evidence_tx.parquet).
Rules (Betsy, Oct 30):
  * Medicare and Medicaid counts only confirm ("yes, they do this"). They never rank anyone by size and are never a price.
  * A provider is held out of the "lowest/highest" rankings ("also listed, may not offer this procedure") only when a public
    volume file covers that kind of provider for that procedure AND it has no record. Everyone else is ranked as before:
      - surgery centers, group practices, imaging centers, labs, clinics: no public volume file covers them
      - hospitals, for procedures Medicare's hospital outpatient file doesn't count (only "comprehensive" groups, so not
        colonoscopy, scans, lab tests)
      - procedures where Medicare is a poor guide (births and maternity, children's care, fertility, birth control,
        vasectomy, sports injuries such as ACL repair): Medicare is mostly people 65+
  * Texas only for now (the proof table is Texas). Other states' pages are unchanged.

status(...) returns (state, record):
  ('proved', rec)       rec = {'src', 'n', 'unit', 'year', 'url', 'group'}: shown as a proof line with link and year
  ('not_covered', why)  ranked as before; why says which rule applied
  ('no_record', why)    held out of the rankings, still listed; why is the plain note shown with it
"""
import io
import re

POOR_GUIDE_CATS = {'Maternity'}
POOR_GUIDE_NAME = re.compile(r'birth|deliver|c-section|cesarean|pregnan|prenatal|newborn|infant|pediatric|child|fertil|ivf|'
                             r'insemination|contracept|iud|implant(?=.*(arm|birth))|vasectomy|tubal|cruciate|acl\b|meniscus repair'
                             r'|well[- ]child|vaccin|immuniz', re.I)
LABEL = {'medicare_physician': 'Medicare', 'medicare_outpatient': 'Medicare', 'medicare_inpatient': 'Medicare',
         'medicaid_professional': 'Medicaid'}
NO_RECORD = ("No Medicare or Medicaid record for this procedure ({year}). That doesn't mean they don't do it: "
             "Medicare is mostly people 65+, and rows under 11 patients are hidden.")


class Proof:
    def __init__(self, s3=None, bucket=None, year='2024', path=None):
        import pyarrow.parquet as pq
        if path:
            tb = pq.read_table(path)
        else:
            body = s3.get_object(Bucket=bucket, Key=f'data/utilization/{year}/evidence_tx.parquet')['Body'].read()
            tb = pq.read_table(io.BytesIO(body))
        d = tb.select(['npi', 'ccn', 'evidence_source', 'code', 'group_name', 'volume', 'unit', 'data_year', 'file_url']).to_pydict()
        self.year = year
        self.code = {}       # (npi, hcpcs) -> best record (Medicare first, then Medicaid)
        self.apc = {}        # (ccn, apc) -> record
        self.drg = {}        # (ccn, drg) -> record
        self.apcs, self.phy_codes = set(), set()
        for i in range(tb.num_rows):
            src = d['evidence_source'][i]
            rec = {'src': LABEL[src], 'n': int(d['volume'][i] or 0), 'unit': d['unit'][i], 'year': d['data_year'][i],
                   'url': d['file_url'][i], 'group': d['group_name'][i] or '',
                   'level_group': src in ('medicare_outpatient', 'medicare_inpatient')}
            if rec['n'] <= 0:
                continue
            c = (d['code'][i] or '').strip()
            if src == 'medicare_outpatient':
                self.apcs.add(c)
                if d['ccn'][i]:
                    self.apc[(d['ccn'][i], c)] = rec
            elif src == 'medicare_inpatient':
                if d['ccn'][i]:
                    self.drg[(d['ccn'][i], c.zfill(3))] = rec
            elif d['npi'][i]:
                if src == 'medicare_physician':
                    self.phy_codes.add(c)
                k = (str(d['npi'][i]), c)
                if k not in self.code or (self.code[k]['src'] == 'Medicaid' and rec['src'] == 'Medicare'):
                    self.code[k] = rec
        self.c2a = {}
        try:
            body = (pq.read_table(path.replace('evidence_tx', 'code_to_apc')) if path else
                    pq.read_table(io.BytesIO(s3.get_object(Bucket=bucket, Key=f'data/utilization/{year}/code_to_apc.parquet')['Body'].read())))
            x = body.to_pydict()
            self.c2a = dict(zip(x['code'], x['apc']))
        except Exception:
            pass

    def status(self, kind, npi, ccn, code, name, cat, drg):
        """kind: the page's provider kind (H hospital, A surgery center, G group/other place, P individual clinician)."""
        if cat in POOR_GUIDE_CATS or POOR_GUIDE_NAME.search(name or ''):
            return 'not_covered', 'Medicare is a poor guide for this procedure (mostly people 65+)'
        npi = str(npi or '')
        rec = self.code.get((npi, code))
        if kind == 'H':
            if drg:
                g = re.sub(r'\D', '', code).zfill(3)
                rec = self.drg.get((ccn, g)) if ccn else None
                if rec:
                    return 'proved', rec
                return ('no_record', NO_RECORD.format(year=self.year)) if ccn else ('not_covered', 'no Medicare hospital ID matched')
            apc = self.c2a.get(code)
            if not apc or apc not in self.apcs:
                return ('proved', rec) if rec else ('not_covered', "Medicare publishes no hospital volume for this kind of procedure")
            hrec = self.apc.get((ccn, apc)) if ccn else None
            if hrec or rec:
                return 'proved', hrec or rec
            return ('no_record', NO_RECORD.format(year=self.year)) if ccn else ('not_covered', 'no Medicare hospital ID matched')
        if kind == 'P':
            if rec:
                return 'proved', rec
            if code in self.phy_codes:
                return 'no_record', NO_RECORD.format(year=self.year)
            return 'not_covered', 'no Medicare volume for this code in Texas'
        if rec:                       # groups and other places: a Medicaid or Medicare record is proof, no record changes nothing
            return 'proved', rec
        return 'not_covered', 'no public volume file covers this kind of provider'


def line(rec):
    """The proof line shown with a provider: 'Medicare: 240 services, 2024' (group-level says so)."""
    g = f" in the procedure group “{rec['group']}”" if rec['group'] and rec['unit'] != 'claim lines' and rec['src'] == 'Medicare' \
        and rec.get('level_group') else ''
    return f"{rec['src']}: {rec['n']:,} {rec['unit']}{g}, {rec['year']}"
