// Executes the GENERATED Apps Script against mocked Google services. Usage: node appsscript_harness.js <script.js>
const fs = require('fs'); const crypto = require('crypto'); const assert = require('assert');
const src = fs.readFileSync(process.argv[2], 'utf8');

function makeSheet(name, rows) {
  const data = rows.map(r => r.slice());
  return {
    data, writes: [], getName: () => name,
    getLastColumn: () => Math.max(...data.map(r => r.length)),
    getLastRow: () => data.length,
    getRange(r, c, nr, nc) {
      const self = this;
      return {
        setValue(v) { while (data[r - 1].length < c) data[r - 1].push(''); data[r - 1][c - 1] = v; self.writes.push([r, c, v]); },
        getValues() { return [data[r - 1].slice(c - 1, c - 1 + (nc || 1))]; }
      };
    },
    getDataRange() { const w = Math.max(...data.map(r => r.length)); return { getValues: () => data.map(r => { const x = r.slice(); while (x.length < w) x.push(''); return x; }) }; }
  };
}
function boot(sheets, fetchImpl, extraSrc, srcOverride) {
  const props = {}; const logs = []; const fetched = [];
  const g = {
    SpreadsheetApp: { getActiveSpreadsheet: () => ({ getSheetByName: n => sheets[n] || null, getSheets: () => Object.values(sheets), getId: () => 'SSID', getName: () => 'Leads' }), flush() {} },
    LockService: { getScriptLock: () => ({ tryLock: () => true, releaseLock() {} }) },
    UrlFetchApp: { fetch: (url, opts) => { fetched.push({ url, opts, body: JSON.parse(opts.payload) }); return fetchImpl(JSON.parse(opts.payload)); } },
    Utilities: { DigestAlgorithm: { MD5: 'md5', SHA_256: 'sha256' }, computeDigest: (a, s) => Array.from(crypto.createHash(a).update(s).digest()).map(b => b > 127 ? b - 256 : b),
      computeHmacSha256Signature: (v, k) => Array.from(crypto.createHmac('sha256', k).update(v).digest()).map(b => b > 127 ? b - 256 : b),
      formatDate: (d, tz, f) => new Date(d.getTime() + 3600000).toISOString().replace('Z', '').slice(0, f.includes('HH') ? 19 : 10) },
    PropertiesService: { getScriptProperties: () => ({ setProperty: (k, v) => { props[k] = v; }, getProperty: k => props[k] }) },
    ScriptApp: { getProjectTriggers: () => (global.__triggers || []), newTrigger: () => ({ timeBased: () => ({ everyMinutes: () => ({ create() {} }) }) }), deleteTrigger() {} },
    Logger: { log: s => logs.push(s) }, console: { log: s => logs.push(String(s)) }
  };
  const fn = new Function(...Object.keys(g), (extraSrc || '') + (srcOverride || src) + '\nreturn {runRecovery_, listCallCenterTriggers, sendNewLeadsToCallCenter, retryRejectedRowsToCallCenter, resendAllRowsToCallCenter, diagnoseMissingLeads, shouldSend_};');
  return { api: fn(...Object.values(g)), logs, fetched, props };
}

// ---------- shouldSend_ decision table ----------
{
  const { api } = boot({}, () => ({}));
  const s = api.shouldSend_;
  assert.strictEqual(s('IMPORTED', 'CC-1', '', 'h', 'normal'), false, 'trusted IMPORTED with order no is skipped');
  assert.strictEqual(s('IMPORTED', '', '', 'h', 'normal'), true, 'IMPORTED without order no must be re-sent');
  assert.strictEqual(s('DUPLICATE', 'CC-1', '', 'h', 'normal'), false);
  assert.strictEqual(s('REJECTED', '', 'h', 'h', 'normal'), false, 'unchanged REJECTED row is not retried every minute');
  assert.strictEqual(s('REJECTED', '', 'old', 'new', 'normal'), true, 'edited REJECTED row is retried');
  assert.strictEqual(s('REJECTED', '', 'h', 'h', 'retryRejected'), true, 'controlled retry');
  assert.strictEqual(s('ERROR', '', '', 'h', 'normal'), true);
  assert.strictEqual(s('', '', '', 'h', 'normal'), true);
  assert.strictEqual(s('IMPORTED', 'CC-1', '', 'h', 'all'), true);
  // bounded retry with exponential backoff for transient ERROR rows
  const now = 1000000;
  assert.strictEqual(s('ERROR', '', 'E1|' + (now + 60000), 'h', 'normal', now), false, 'backing off: not yet due');
  assert.strictEqual(s('ERROR', '', 'E1|' + (now - 1), 'h', 'normal', now), true, 'due again');
  assert.strictEqual(s('ERROR', '', 'E6|' + (now - 1), 'h', 'normal', now), false, 'max attempts reached: stops retrying');
  assert.strictEqual(s('ERROR', '', 'E6|' + (now - 1), 'h', 'retryRejected', now), true, 'controlled retry still possible');
}

// ---------- full sync run ----------
{
  const H = ['Order ID', 'Full Name', 'Phone', 'SKU', 'Product Quantity', 'Total Price', 'Date', 'CALL CENTER IMPORT STATUS', 'CALL CENTER ORDER ID', 'CALL CENTER IMPORT ERROR', 'CALL CENTER ROW HASH'];
  const rows = [H,
    ['A1', 'Alice', '0611111111', 'SKU1', 1, 100, '2026-10-31', 'IMPORTED', 'CC-A1', '', ''],   // trusted -> skipped
    ['A2', 'Bob', '0622222222', 'SKU1', 1, 100, '2026-10-31', 'IMPORTED', '', '', ''],          // false IMPORTED -> resent
    ['A3', 'Cara', '0633333333', '', 1, 100, '2026-10-31', 'REJECTED', '', 'Product SKU not found: (empty)', 'stale'], // edited -> resent
    ['', 'Dan', '0644444444', 'SKU1', 2, 200, '2026-11-01', '', '', '', ''],                    // blank id -> resent, no row-based id
    ['A5', 'Eve', '', 'SKU1', 1, 100, '2026-11-01', '', '', '', ''],                            // no phone -> SKIPPED, not sent
  ];
  const sheet = makeSheet('orders', rows);
  const { api, logs, fetched, props } = boot({ orders: sheet }, body => ({
    getResponseCode: () => 200,
    getContentText: () => JSON.stringify({ results: body.orders.map(o => ({ row_number: o.row_number, status: 'IMPORTED', outcome: o.row_number === 4 ? 'REJECTED' : 'INSERTED', order_number: 'CC-' + o.row_number, error: o.row_number === 4 ? 'Product SKU not found: (empty)' : '' })) })
  }));
  api.sendNewLeadsToCallCenter();
  assert.strictEqual(fetched.length, 1);
  assert.strictEqual(fetched[0].opts.headers['X-Webhook-Token'].length > 0, true);
  assert.ok(!fetched[0].url.includes('token='), 'token must not be in URL');
  const sent = fetched[0].body.orders;
  assert.deepStrictEqual(sent.map(o => o.row_number), [3, 4, 5], 'rows 3,4,5 sent; trusted IMPORTED row 2 and phone-less row 6 are not');
  assert.ok(sent.every(o => !String(o.external_order_id).startsWith('sheet:')), 'row position is never used as identity');
  assert.strictEqual(sent.find(o => o.row_number === 5).external_order_id, '');
  assert.strictEqual(sent.find(o => o.row_number === 5).lead_date, '2026-11-01');
  assert.strictEqual(sent.find(o => o.row_number === 5).quantity, 2, 'Product Quantity header is recognised');
  assert.strictEqual(sent.find(o => o.row_number === 5).total_price, 200, 'Total Price header is recognised');
  assert.deepStrictEqual(Object.keys(fetched[0].body.client).sort(), ['spreadsheet', 'tab', 'version']);
  assert.strictEqual(fetched[0].body.client.spreadsheet, crypto.createHash('md5').update('SSID').digest('hex').slice(0, 6));
  const st = i => sheet.data[i - 1][7];
  assert.strictEqual(st(2), 'IMPORTED'); assert.strictEqual(st(3), 'IMPORTED'); assert.strictEqual(st(4), 'REJECTED'); assert.strictEqual(st(5), 'IMPORTED');
  assert.strictEqual(st(6), 'SKIPPED'); assert.ok(sheet.data[5][9].includes('phone'));
  assert.ok(sheet.data[3][10] && sheet.data[3][10] !== 'stale', 'rejected row stores its hash');
  const stats = JSON.parse(props.LAST_SYNC);
  assert.deepStrictEqual([stats.sent, stats.inserted, stats.rejected, stats.skipped, stats.unchanged], [3, 2, 1, 1, 1]);

  // second tick: nothing is re-sent (REJECTED unchanged, others trusted) -> no repeated retries of permanent rows
  const before = fetched.length; api.sendNewLeadsToCallCenter();
  assert.strictEqual(fetched.length, before + 0 + (fetched.length > before ? 0 : 0));
  assert.ok(fetched.length === before || fetched[fetched.length - 1].body.orders.every(o => o.row_number === 6 || false) === false);
  assert.strictEqual(fetched.length, before, 'no HTTP call when nothing is eligible');
  // controlled retry path
  api.retryRejectedRowsToCallCenter();
  assert.deepStrictEqual(fetched[fetched.length - 1].body.orders.map(o => o.row_number), [4]);
}

// ---------- Sheet-2 shape: "First Name" header, NO Order ID column, tab pinned by gid ----------
{
  const H = ['Product SKU', 'First Name', 'Phone', 'City', 'Product Quantity', 'Total Price', 'Product Name', 'CALL CENTER IMPORT STATUS', 'CALL CENTER ORDER ID', 'CALL CENTER IMPORT ERROR', 'CALL CENTER ROW HASH'];
  const sheet = makeSheet('orders', [H, ['TOPLUX-BSC-940-60', 'Sam', '0612121212', 'Fes', 2, 299, 'blood sugar', '', '', '', '']]);
  sheet.getSheetId = () => 1490835622;
  const other = makeSheet('easysell_abandoneds', [['x']]); other.getSheetId = () => 1708130206;
  const { api, fetched } = boot({ orders: sheet, easysell_abandoneds: other }, body => ({ getResponseCode: () => 200, getContentText: () => JSON.stringify({ results: body.orders.map(o => ({ row_number: o.row_number, status: 'IMPORTED', outcome: 'INSERTED', order_number: 'CC-X' })) }) }));
  api.sendNewLeadsToCallCenter();
  const o = fetched[0].body.orders[0];
  assert.strictEqual(o.customer_name, 'Sam', 'First Name header is recognised'); assert.strictEqual(o.external_order_id, '', 'no Order ID column => no row-based identity');
  assert.strictEqual(o.quantity, 2); assert.strictEqual(o.total_price, 299);
  assert.strictEqual(sheet.data[1][7], 'IMPORTED'); assert.strictEqual(sheet.data[1][8], 'CC-X');
}

// ---------- cutover safeguards: wrong-spreadsheet guard, missing-header failure, held rows, heartbeat, failure recording ----------
{
  const H = ['Product SKU', 'First Name', 'Phone', 'City', 'Product Quantity', 'Total Price', 'Product Name', 'CALL CENTER IMPORT STATUS', 'CALL CENTER ORDER ID', 'CALL CENTER IMPORT ERROR', 'CALL CENTER ROW HASH'];
  const mk = () => makeSheet('orders', [H, ['SKU1', 'Held', '0611111111', 'X', 1, 199, 'p', 'ERROR', '', 'Product SKU not found: (empty)', ''], ['SKU1', 'Go', '0622222222', 'X', 2, 249, 'p', '', '', '', '']]);
  const ok = body => ({ getResponseCode: () => 200, getContentText: () => JSON.stringify({ results: body.orders.map(o => ({ row_number: o.row_number, status: 'IMPORTED', outcome: 'INSERTED', order_number: 'CC-N' })) }) });
  function bootCustom(replace, sheets, fetchImpl) {
    const saved = require('fs').readFileSync(process.argv[2], 'utf8'); let t = saved; Object.keys(replace).forEach(k => { assert.ok(t.includes(k), 'missing ' + k); t = t.replace(k, replace[k]); });
    return boot(sheets, fetchImpl, '', t);
  }
  // 1) HOLD_ROWS: held row 2 is never sent or modified; row 3 goes out
  { const sheet = mk(); const { api, fetched } = bootCustom({ 'const HOLD_ROWS = [];': 'const HOLD_ROWS = [2];' }, { orders: sheet }, ok);
    api.sendNewLeadsToCallCenter();
    assert.deepStrictEqual(fetched[0].body.orders.map(o => o.row_number), [3]); assert.strictEqual(sheet.data[1][7], 'ERROR', 'held row untouched'); assert.strictEqual(sheet.data[1][9], 'Product SKU not found: (empty)'); }
  // 2) wrong spreadsheet: refuses to run, sends nothing, records LAST_ERROR
  { const sheet = mk(); const { api, fetched, props } = bootCustom({ "const EXPECTED_SPREADSHEET_PREFIX = '';": "const EXPECTED_SPREADSHEET_PREFIX = 'aaaaaa';" }, { orders: sheet }, ok);
    assert.throws(() => api.sendNewLeadsToCallCenter(), /Wrong spreadsheet/); assert.strictEqual(fetched.length, 0); assert.ok(JSON.parse(props.LAST_ERROR).message.includes('Wrong spreadsheet')); }
  // 3) a renamed/missing required header fails loudly instead of skipping every row
  { const sheet = makeSheet('orders', [['Product SKU', 'Nombre', 'Phone', 'CALL CENTER IMPORT STATUS', 'CALL CENTER ORDER ID', 'CALL CENTER IMPORT ERROR', 'CALL CENTER ROW HASH'], ['SKU1', 'Go', '0622222222', '', '', '', '']]);
    const { api, fetched, props } = bootCustom({}, { orders: sheet }, ok);
    assert.throws(() => api.sendNewLeadsToCallCenter(), /Required column not found for "customer_name"/); assert.strictEqual(fetched.length, 0); assert.strictEqual(sheet.writes.length, 0, 'nothing written'); assert.ok(props.LAST_ERROR); }
  // 4) heartbeat: idle feed pings CODOPS (empty batch) at most every PING_MINUTES
  { const sheet = makeSheet('orders', [H, ['SKU1', 'Done', '0633333333', 'X', 1, 199, 'p', 'IMPORTED', 'CC-1', '', '']]);
    const { api, fetched, props } = bootCustom({}, { orders: sheet }, ok);
    api.sendNewLeadsToCallCenter(); assert.strictEqual(fetched.length, 1); assert.deepStrictEqual(fetched[0].body.orders, []); assert.ok(fetched[0].body.client.spreadsheet);
    api.sendNewLeadsToCallCenter(); assert.strictEqual(fetched.length, 1, 'no second ping within the interval'); assert.ok(props.LAST_PING); }
}

// ---------- dry run is truly write-free, even when the CALL CENTER ROW HASH header is missing ----------
{
  const H = ['Product SKU', 'Full Name', 'Phone', 'City', 'Product Quantity', 'Total Price', 'Product Name', 'Order ID', 'CALL CENTER IMPORT STATUS', 'CALL CENTER ORDER ID', 'CALL CENTER IMPORT ERROR'];
  const sheet = makeSheet('orders', [H, ['SKU1', 'Done', '0633333333', 'X', 2, 249, 'p', '1001', 'IMPORTED', 'CC-1', '']]);
  const { api, fetched } = boot({ orders: sheet }, body => ({ getResponseCode: () => 200, getContentText: () => JSON.stringify({ results: body.orders.map(o => ({ row_number: o.row_number, status: 'IMPORTED', outcome: 'DUPLICATE', order_number: 'CC-1' })) }) }));
  api.runRecovery_([2], true);
  assert.ok(fetched[0].url.endsWith('?dry_run=true')); assert.strictEqual(sheet.writes.length, 0, 'dry run must not write any cell, including a missing helper header');
  assert.strictEqual(sheet.data[0].length, H.length, 'header row untouched');
  api.sendNewLeadsToCallCenter();                     // the first REAL tick adds the one helper header
  assert.deepStrictEqual(sheet.writes.map(w => w.slice(0, 2)), [[1, 12]]); assert.strictEqual(sheet.data[0][11], 'CALL CENTER ROW HASH');
}

// ---------- targeted recovery: dry run writes nothing; apply sends only the listed rows ----------
{
  const H = ['Order ID', 'Full Name', 'Phone', 'SKU', 'Product Quantity', 'Total Price', 'CALL CENTER IMPORT STATUS', 'CALL CENTER ORDER ID', 'CALL CENTER IMPORT ERROR', 'CALL CENTER ROW HASH'];
  const rows = [H,
    ['1046', 'A', '0611111111', 'SKU1', 1, 100, 'IMPORTED', 'CC-OWNER', '', ''],   // row 2: genuinely imported
    ['1046', 'B', '0622222222', 'SKU1', 1, 100, 'IMPORTED', 'CC-OWNER', '', ''],   // row 3: falsely IMPORTED (someone else's number)
    ['1047', 'C', '0633333333', 'SKU1', 2, 200, 'IMPORTED', 'CC-C', '', ''],       // row 4: fine, must NOT be sent
  ];
  const sheet = makeSheet('orders', rows);
  const urls = [];
  const { api, fetched } = boot({ orders: sheet }, body => ({
    getResponseCode: () => 200,
    getContentText: () => JSON.stringify({ results: body.orders.map(o => ({ row_number: o.row_number, status: 'IMPORTED', outcome: urls[urls.length - 1].includes('dry_run') ? 'WOULD_INSERT' : 'INSERTED', collision: true, order_number: urls[urls.length - 1].includes('dry_run') ? '' : 'CC-NEW' })) })
  }));
  const origFetch = fetched.push.bind(fetched); fetched.push = (x) => { urls.push(x.url); return origFetch(x); };
  api.runRecovery_([3], true);
  assert.strictEqual(fetched.length, 1); assert.ok(fetched[0].url.endsWith('?dry_run=true'));
  assert.deepStrictEqual(fetched[0].body.orders.map(o => o.row_number), [3], 'only the listed row is sent');
  assert.strictEqual(sheet.writes.length, 0, 'dry run never writes to the sheet');
  api.runRecovery_([3], false);
  assert.ok(!fetched[1].url.includes('dry_run'));
  assert.strictEqual(sheet.data[2][6], 'IMPORTED'); assert.strictEqual(sheet.data[2][7], 'CC-NEW', 'apply records the new order number');
  assert.strictEqual(sheet.data[1][7], 'CC-OWNER', 'the original row is untouched');
  assert.throws(() => api.runRecovery_([], false), /empty/);
}

// ---------- transient failure: backoff state recorded, no immediate resend, attempts capped ----------
{
  const H = ['Order ID', 'Full Name', 'Phone', 'SKU', 'Product Quantity', 'Total Price', 'CALL CENTER IMPORT STATUS', 'CALL CENTER ORDER ID', 'CALL CENTER IMPORT ERROR', 'CALL CENTER ROW HASH'];
  const sheet = makeSheet('orders', [H, ['T1', 'Tia', '0655555555', 'SKU1', 1, 100, '', '', '', '']]);
  const { api, fetched, props } = boot({ orders: sheet }, body => ({
    getResponseCode: () => 200,
    getContentText: () => JSON.stringify({ results: body.orders.map(o => ({ row_number: o.row_number, status: 'ERROR', outcome: 'FAILED', error: 'Concurrent import conflict; will be retried' })) })
  }));
  api.sendNewLeadsToCallCenter();
  assert.strictEqual(sheet.data[1][6], 'ERROR');
  assert.ok(/^E1\|\d+$/.test(sheet.data[1][9]), 'attempt counter + next retry stored: ' + sheet.data[1][9]);
  const before = fetched.length; api.sendNewLeadsToCallCenter();
  assert.strictEqual(fetched.length, before, 'backing off: not re-sent on the very next tick');
  assert.strictEqual(JSON.parse(props.LAST_SYNC).sent, 0);
}

// ---------- diagnoseMissingLeads: the Order-ID 1046 collision scenario ----------
{
  const H = ['Date', 'Full Name', 'Phone', 'SKU', 'Quantity', 'Total', 'City', 'Order ID', 'CALL CENTER IMPORT STATUS', 'CALL CENTER ORDER ID', 'CALL CENTER IMPORT ERROR'];
  const d = s => new Date(s);
  const rows = [H,
    [d('2026-10-30T20:00:00Z'), 'SecretA', '0611110006', 'NOVAMAN2026', 1, 199, 'X', '1046', 'IMPORTED', 'CC-A', ''],   // OWNER
    [d('2026-10-31T20:00:00Z'), 'SecretB', '0622220099', 'NOVAMAN2026', 1, 199, 'X', '1046', 'IMPORTED', 'CC-A', ''],   // same id + same order no, other customer
    [d('2026-11-01T09:00:00Z'), 'SecretC', '0633330098', 'NOVAMAN2026', 1, 199, 'X', '1046', 'IMPORTED', 'CC-A', ''],   // same again
    [d('2026-10-31T10:00:00Z'), 'SecretD', '0644440007', 'NOVAMAN2026', 1, 199, 'X', '1047', 'IMPORTED', 'CC-B', ''],   // OK
    [d('2026-11-01T10:00:00Z'), 'SecretE', '0655550008', 'NOVAMAN2026', 1, 199, 'X', '2755', 'IMPORTED', 'CC-C', ''],   // OK
    [d('2026-11-01T11:00:00Z'), 'SecretF', '0666660010', 'NOVAMAN2026', 1, 199, 'X', '2760', '', '', ''],              // never imported
    [d('2026-11-01T12:00:00Z'), 'SecretG', '', 'NOVAMAN2026', 1, 199, 'X', '2761', '', '', ''],                         // silent skip (no phone)
    [d('2026-11-01T13:00:00Z'), 'SecretH', '0611110006', 'NOVAMAN2026', 2, 398, 'X', '2762', '', '', ''],              // same phone as row 2, DIFFERENT order -> legit
    [d('2026-11-01T14:00:00Z'), 'SecretI', '0677770011', 'WRONGSKU', 1, 199, 'X', '2763', 'IMPORTED', '', ''],          // IMPORTED without order no
  ];
  const sheet = makeSheet('orders', rows);
  const known = "var DIAG_KEY = 'k';\n" + 'var CODOPS_KNOWN = {"CC-A":["1046","0006","NOVAMAN2026","2026-10-30"],"CC-B":["1047","0007","NOVAMAN2026","2026-10-31"],"CC-C":["2755","0008","NOVAMAN2026","2026-11-01"]};\nvar CODOPS_SKUS = ["NOVAMAN2026","TOPLUX-BSC-940-60"];\n';
  const { api, logs, fetched } = boot({ orders: sheet, Sheet1: makeSheet('Sheet1', [['x']]) }, () => { throw new Error('diagnose must not call the network'); }, known);
  api.diagnoseMissingLeads();
  const out = logs.join('\n');
  assert.strictEqual(fetched.length, 0, 'no network'); assert.strictEqual(sheet.writes.length, 0, 'diagnose writes nothing');
  assert.ok(!/Secret[A-I]|0611110006|0622220099|0633330098|0655550008|0666660010/.test(out), 'no PII in output');
  assert.ok(out.includes('external_order_id => H "Order ID"'), 'mapping with column letter\n' + out);
  assert.ok(out.includes('sku => D "SKU"') && out.includes('phone => C "Phone"') && out.includes('lead_date => A "Date"'));
  // 1. repeated ids
  assert.ok(out.includes('id 1046 [DIFFERENT_LEADS_SHARE_ID]'), out);
  assert.ok(out.includes('row 2:IMPORTED:CC-A OWNER') && out.includes('row 3:IMPORTED:CC-A ORPHAN(no own order)') && out.includes('row 4:IMPORTED:CC-A ORPHAN(no own order)'));
  // 2. shared order number
  assert.ok(/CC-A -> row 2\(ext 1046,IMPORTED,OWNER\) ; row 3\(ext 1046,IMPORTED,ORPHAN\) ; row 4\(ext 1046,IMPORTED,ORPHAN\)/.test(out), out);
  assert.ok(out.includes('SHARING ONE CODOPS ORDER NUMBER: 1 order numbers'));
  // 3. IMPORTED without real order: rows 3,4 (other customer) and 9 (no order no)
  assert.ok(out.includes('MARKED IMPORTED/DUPLICATE WITHOUT A MATCHING REAL CODOPS ORDER: 3'), out);
  assert.ok(out.includes('ORDER_NO_BELONGS_TO_OTHER_CUSTOMER: 2 rows -> 3,4') && out.includes('NO_ORDER_NO: 1 rows -> 10'));
  // 4. missing per day (exact dates): 10-31 -> row 3 ; 11-01 -> rows 4,7,8(skipped),9,10
  assert.ok(/2026-10-31  <== IN SCOPE: 1 rows/.test(out) && /2026-11-01  <== IN SCOPE: 5 rows/.test(out), out);
  // 5. skipped
  assert.ok(out.includes('silently skipped (missing name/phone): 1 rows 8'));
  assert.ok(out.includes('never imported (blank/other status): 2 rows 7,9'));
  // 6. SKU check
  assert.ok(out.includes('WRONGSKU: 1  <== NOT A CODOPS PRODUCT'));
  // 7. same phone: row 2 and row 8 share a phone but are different orders -> legitimate, not a duplicate
  assert.ok(out.includes('(legitimate distinct orders): 1 e.g. rows 2/9'), out);
  assert.ok(out.includes('(likely true duplicate rows): 0'));
  // server-side verification table: digests only, deterministic, no phone numbers
  const begin = out.split('DIGESTS_BEGIN')[1].split('DIGESTS_END')[0].trim().split('\n');
  assert.strictEqual(begin[0], 'row|ext|status|orderNo|sku|qty|total|digest');
  const expect = crypto.createHmac('sha256', 'k').update('611110006').digest('hex').slice(0, 12);
  assert.ok(begin.includes('2|1046|IMPORTED|CC-A|NOVAMAN2026|1|199|' + expect), begin.join('\n'));
  assert.ok(begin.some(l => l.startsWith('8|2761|') && l.endsWith('|NOPHONE')));
}

// ---------- trigger inventory is read-only and token-safe ----------
{
  global.__triggers = [{ getHandlerFunction: () => 'sendNewLeadsToCallCenter', getEventType: () => 'CLOCK', getTriggerSource: () => 'CLOCK', getUniqueId: () => 'T1' }];
  const sheet = makeSheet('orders', [['x']]);
  const pre = "var CALL_CENTER_WEBHOOK = 'https://api.example.com/api/v1/integrations/google-sheets/abcdef12-0000/webhook?token=SUPERSECRETTOKEN';\n";
  // legacy script style: token embedded in the URL (diagnostic code only, so the constants do not clash)
  const diagOnly = src.slice(src.indexOf('/**\n * READ-ONLY diagnostic.'));
  const { api, logs } = boot({ orders: sheet }, () => { throw new Error('no network'); }, pre, diagOnly.replace(/function sendNew[\s\S]*$/, '') + '\nfunction sendNewLeadsToCallCenter(){}\nfunction retryRejectedRowsToCallCenter(){}\nfunction resendAllRowsToCallCenter(){}\nfunction shouldSend_(){}\nfunction runRecovery_(){}');
  api.listCallCenterTriggers();
  const o = logs.join('\n');
  assert.ok(o.includes('handler sendNewLeadsToCallCenter') && o.includes('id-hash ' + crypto.createHash('md5').update('SSID').digest('hex').slice(0, 6)));
  assert.ok(!o.includes('SUPERSECRETTOKEN') && o.includes('token embedded in URL') && o.includes('Token fingerprint: '), o);
  assert.strictEqual(sheet.writes.length, 0);
  delete global.__triggers;
}
console.log('APPS_SCRIPT_HARNESS_OK');
