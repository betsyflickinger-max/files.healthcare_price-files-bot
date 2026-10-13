import { due } from './worker.js';
const t = (c, iso, want) => { const got = due(c, new Date(iso)); if (got !== want) { console.log('FAIL', c, iso, got); process.exitCode = 1; } };
t('7,22,37,52 * * * *', '2026-10-13T22:22:00Z', true); t('7,22,37,52 * * * *', '2026-10-13T22:23:00Z', false);
t('*/10 * * * *', '2026-10-13T22:40:00Z', true); t('*/10 * * * *', '2026-10-13T22:41:00Z', false);
t('47 */6 * * *', '2026-10-13T18:47:00Z', true); t('47 */6 * * *', '2026-10-13T19:47:00Z', false);
t('17 * 20-28 * *', '2026-10-21T05:17:00Z', true); t('17 * 20-28 * *', '2026-10-13T05:17:00Z', false);
t('41 7 * * 0', '2026-10-18T07:41:00Z', true); t('41 7 * * 0', '2026-10-19T07:41:00Z', false);
t('11 13 5 * *', '2026-11-05T13:11:00Z', true);
console.log(process.exitCode ? 'failed' : 'all cron tests pass');
