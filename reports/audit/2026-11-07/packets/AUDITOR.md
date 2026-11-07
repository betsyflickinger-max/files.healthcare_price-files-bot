# Auditor instructions (Layer 3 sample audit)

You are auditing price lines on The Healthcare Files (files.healthcare) before it opens to the public. You did not build this
data. Judge only what the packet shows. Never fix anything; report.

For each packet, answer in results.csv (one row per packet, keep the packet id):

1. **page_ok**: does the page data line match what the published page says about this provider? (amount, insurer/network,
   provider) yes / no / not on a published page (fine for non-featured codes) / can't tell
2. **source_ok**: does the source (insurer table row or hospital file line) carry the same code, provider and amount? yes / no / can't tell
3. **place_ok**: is the provider really in the page's state and area (NPI Registry practice address)? yes / no / can't tell
4. **insurer_ok**: does the file's own insurer name match the insurer shown? yes / no / can't tell
5. **meaning_ok**: is the amount labeled right: facility vs doctor fee, in vs out of network, per day/per unit vs whole service,
   modifier (part only), capitation/bundle, expired, percent of charges? yes / no / can't tell. Plausible for this kind of
   provider (an audiologist with a colonoscopy rate is a "ghost rate": say so in the note)?
6. **link_ok**: does the page's source link name the same file the source rows came from? yes / no / can't tell
7. **fresh_ok**: is the file date shown, and if it's older than 6 months, is that obvious? yes / no
8. **verdict**: Pass / Critical / Major / Minor
   - Critical: wrong amount; wrong provider, insurer, network, code or state; out-of-network shown as in-network; one
     hospital's file on another hospital
   - Major: dead or wrong link; missing/wrong date; wrong or missing label (per day shown as total, part-only fee, capitation)
   - Minor: name formatting, typos
9. **note**: one sentence on why (required for anything but Pass).

"Can't tell" is an honest answer; never guess. Work in batches of 25 (one batch file per session).
