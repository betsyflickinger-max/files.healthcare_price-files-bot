// Upfront bot timer (Cloudflare Worker, Oct 13, 2026). GitHub's free schedule skips runs when GitHub is busy (on Oct 13
// none fired for hours), so this Worker starts each bot workflow at its time instead. It runs every minute, checks the
// table below (times in UTC, same as the workflows' own cron lines) and asks GitHub to start what is due.
// GitHub's own schedules stay in the workflows as a backup; every workflow that matters has a run lock, so a double start waits.
// Secret GH_TOKEN: a fine-grained GitHub token for betsyflickinger-max/price-files-bot with "Actions: read and write".
const REPO = 'betsyflickinger-max/price-files-bot';
const JOBS = [
  ['7,22,37,52 * * * *', 'board-status.yml'],
  ['*/10 * * * *', 'insurers.yml', { dry_run: 'false', fill: 'true' }],          // quick fill: collect results, start waiting files
  ['47 */6 * * *', 'insurers.yml', { dry_run: 'false', scheduled: 'true' }],     // full check for new insurer files
  ['19 */6 * * *', 'inventory-backfill.yml'],
  ['29 */6 * * *', 'site-build.yml'],
  ['41 * * * *', 'state-pages.yml'],
  ['17 * 20-28 * *', 'hosp-areas.yml'],
  ['17 9 * * *', 'hospitals.yml'],
  ['37 9 * * *', 'names.yml', { max_codes: '20000' }],
  ['53 11 * * *', 'census-report.yml'],
  ['23 13 * * *', 'calculator.yml'],
  ['40 16 * * *', 'dashboard.yml'],
  ['41 7 * * 0', 'find-sites.yml'],
  ['11 13 5 * *', 'plans.yml'],
];

function part(spec, v, min, max) {
  return spec.split(',').some(p => {
    let [range, step] = p.split('/'); step = step ? +step : 1;
    let lo = min, hi = max;
    if (range !== '*') { const [a, b] = range.split('-'); lo = +a; hi = b === undefined ? (p.includes('/') ? max : +a) : +b; }
    return v >= lo && v <= hi && (v - lo) % step === 0;
  });
}
function due(cron, d) {
  const [mi, h, dom, mo, dow] = cron.split(/\s+/);
  return part(mi, d.getUTCMinutes(), 0, 59) && part(h, d.getUTCHours(), 0, 23) && part(dom, d.getUTCDate(), 1, 31) &&
         part(mo, d.getUTCMonth() + 1, 1, 12) && part(dow, d.getUTCDay(), 0, 6);
}
async function start(env, wf, inputs) {
  if (!env.GH_TOKEN) { console.log('GH_TOKEN not set; would start', wf); return; }
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${wf}/dispatches`, {
    method: 'POST', body: JSON.stringify({ ref: 'main', inputs: inputs || {} }),
    headers: { Authorization: `Bearer ${env.GH_TOKEN}`, Accept: 'application/vnd.github+json', 'User-Agent': 'upfront-bot-timer',
               'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json' } });
  console.log(wf, JSON.stringify(inputs || {}), r.status, r.status === 204 ? 'started' : (await r.text()).slice(0, 200));
}
export default {
  async scheduled(event, env, ctx) {
    const d = new Date(event.scheduledTime);
    for (const [cron, wf, inputs] of JOBS) if (due(cron, d)) ctx.waitUntil(start(env, wf, inputs));
  },
  async fetch() { return new Response('upfront bot timer: ok', { headers: { 'content-type': 'text/plain' } }); },
};
export { due };
