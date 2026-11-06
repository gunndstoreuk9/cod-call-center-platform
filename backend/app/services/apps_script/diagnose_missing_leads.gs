/**
 * READ-ONLY diagnostic. Paste into the EXISTING Apps Script project of the lead sheet.
 * It never sends orders, never writes a cell, never touches triggers, and never prints names,
 * phones or addresses: only row numbers, counts, SKUs, order ids and CODOPS order numbers.
 *
 * Optional but recommended: also paste codops_known_orders.gs (read-only export of real CODOPS order
 * numbers) as a second file. With it the script can prove whether a row marked IMPORTED has a real order.
 *
 * Run: Apps Script editor -> select diagnoseMissingLeads -> Run -> View > Logs (Execution log).
 */
function diagnoseMissingLeads() {
  var TZ = 'Africa/Casablanca';
  var DAYS = ['2026-10-30', '2026-10-31', '2026-11-01'];
  var DIAG_SHEET_NAME = ''; // leave empty: uses SOURCE_SHEET_NAME if defined, else 'orders'
  var ALIASES = {
    sku: ['SKU', 'Product SKU', 'Lineitem sku', 'Variant SKU'],
    customer_name: ['FULL NAME', 'Full Name', 'First Name', 'Name', 'Customer Name', 'Shipping Name'],
    phone: ['PHONE NUMBER', 'Phone Number', 'Phone', 'Mobile', 'Shipping Phone'],
    city: ['CITY', 'City', 'Shipping City'],
    address: ['ADDRESS', 'Address', 'Shipping Address', 'Address1'],
    quantity: ['QUANTITY', 'Quantity', 'Product Quantity', 'Qty', 'Lineitem quantity'],
    total_price: ['TOTAL PRICE MAD', 'Total Price MAD', 'Total Price', 'Total', 'Price', 'Amount'],
    external_order_id: ['SHOPIFY ORDER ID', 'Shopify Order ID', 'Order ID', 'Order Number', 'Order Name'],
    lead_date: ['DATE', 'Date', 'Created At', 'Created', 'Timestamp', 'Order Date', 'Date Created', 'Created Time', 'Lead Date']
  };
  var STATUS_H = 'CALL CENTER IMPORT STATUS', ORDER_H = 'CALL CENTER ORDER ID', ERROR_H = 'CALL CENTER IMPORT ERROR';
  var out = [];
  function log(s) { out.push(s); }
  function norm(v) { return String(v === null || v === undefined ? '' : v).trim().toLowerCase(); }
  function letter(i) { var s = '', n = i + 1; while (n > 0) { var m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); } return s; }
  function cap(arr, n) { return arr.length > n ? arr.slice(0, n).join(',') + ',...(+' + (arr.length - n) + ')' : arr.join(','); }

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  log('=== diagnoseMissingLeads v2 (READ-ONLY) ===');
  log('Spreadsheet tabs (name : data rows):');
  ss.getSheets().forEach(function (s) { log('  - "' + s.getName() + '" : ' + Math.max(s.getLastRow() - 1, 0)); });
  var configured = (typeof SOURCE_SHEET_NAME !== 'undefined') ? SOURCE_SHEET_NAME : null;
  var wanted = DIAG_SHEET_NAME || configured || 'orders';
  log('Importer SOURCE_SHEET_NAME: ' + (configured === null ? '(not defined in this project)' : '"' + configured + '"') + ' | inspecting "' + wanted + '"');
  var sheet = ss.getSheetByName(wanted);
  if (!sheet) { log('!! Tab "' + wanted + '" NOT FOUND'); Logger.log(out.join('\n')); return; }
  if (configured !== null && configured !== 'orders') log('!! importer reads "' + configured + '" but the lead tab should be "orders"');

  var known = (typeof CODOPS_KNOWN !== 'undefined') ? CODOPS_KNOWN : null;
  var knownSkus = (typeof CODOPS_SKUS !== 'undefined') ? CODOPS_SKUS.map(function (s) { return s.toUpperCase(); }) : null;
  log('CODOPS reference data: ' + (known ? Object.keys(known).length + ' real GOOGLE_SHEETS orders loaded' : 'NOT loaded (paste codops_known_orders.gs to verify IMPORTED marks)'));

  var values = sheet.getDataRange().getValues();
  if (values.length < 2) { log('No data rows.'); Logger.log(out.join('\n')); return; }
  var headers = values[0].map(function (v) { return String(v || '').trim(); });
  var nh = headers.map(norm);
  function resolve(aliases) { for (var i = 0; i < aliases.length; i++) { var k = nh.indexOf(norm(aliases[i])); if (k >= 0) return k; } return -1; }

  // ---- 6. header / SKU mapping -------------------------------------------------
  var col = {};
  log('');
  log('--- HEADER MAPPING (field => column letter "header") ---');
  Object.keys(ALIASES).forEach(function (key) {
    col[key] = resolve(ALIASES[key]);
    log('  ' + key + ' => ' + (col[key] >= 0 ? letter(col[key]) + ' "' + headers[col[key]] + '"' : 'NOT FOUND (tried ' + ALIASES[key].join(' | ') + ')'));
  });
  col.status = nh.indexOf(norm(STATUS_H)); col.order = nh.indexOf(norm(ORDER_H)); col.error = nh.indexOf(norm(ERROR_H));
  log('  import status => ' + (col.status >= 0 ? letter(col.status) : 'absent') + ' | codops order no => ' + (col.order >= 0 ? letter(col.order) : 'absent') + ' | error => ' + (col.error >= 0 ? letter(col.error) : 'absent'));
  var usedIdx = Object.keys(col).map(function (k) { return col[k]; });
  log('  all headers: ' + headers.map(function (h, i) { return letter(i) + '=' + (h || '(blank)') + (usedIdx.indexOf(i) >= 0 ? '*' : ''); }).join(' | ') + '   (* = used)');
  if (col.phone < 0 || col.customer_name < 0) log('!! phone or name header NOT resolved: the old importer silently skips EVERY row');
  if (col.sku < 0) log('!! SKU header NOT resolved: every row is sent with an empty SKU and rejected (unless a default product exists)');
  if (col.external_order_id < 0) log('!! Order ID header NOT resolved');
  if (col.lead_date < 0) log('!! no date column: day attribution below is ESTIMATED from neighbouring verified orders');

  function cell(row, c) { return c >= 0 ? row[c] : ''; }
  function dayOf(v) {
    if (v === '' || v === null || v === undefined) return '';
    var d = (v instanceof Date) ? v : null;
    if (!d) {
      var s = String(v).trim(), m = s.match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{4})/);
      if (m) return m[3] + '-' + ('0' + m[2]).slice(-2) + '-' + ('0' + m[1]).slice(-2);
      d = new Date(s); if (isNaN(d.getTime())) return '';
    }
    return Utilities.formatDate(d, TZ, 'yyyy-MM-dd');
  }
  function digits(v) { return String(v || '').replace(/\D/g, ''); }

  // ---- parse rows (PII is reduced to booleans / keys; never printed) ------------
  var recs = [];
  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    if (!row.some(function (v) { return String(v || '').trim() !== ''; })) continue;
    var ph = digits(cell(row, col.phone));
    recs.push({
      row: r + 1, ext: String(cell(row, col.external_order_id) || '').trim(),
      st: String(cell(row, col.status) || '').trim().toUpperCase(), orderNo: String(cell(row, col.order) || '').trim(),
      hasName: String(cell(row, col.customer_name) || '').trim() !== '', hasPhone: ph !== '',
      pk: ph.slice(-9), l4: ph.slice(-4), sku: String(cell(row, col.sku) || '').trim(),
      qty: String(cell(row, col.quantity) || ''), total: String(cell(row, col.total_price) || ''),
      date: dayOf(cell(row, col.lead_date)), err: String(cell(row, col.error) || '').slice(0, 60)
    });
  }
  var byRow = {}; recs.forEach(function (x) { byRow[x.row] = x; });
  log('');
  log('Non-empty data rows: ' + recs.length);

  // ---- index of real CODOPS orders by external id -------------------------------
  var knownByExt = {};
  if (known) Object.keys(known).forEach(function (no) { var k = known[no]; if (k[0]) (knownByExt[k[0]] = knownByExt[k[0]] || []).push({ no: no, l4: k[1] }); });

  // match of a row against REAL orders
  function verdict(x) {
    if (!known) return x.orderNo ? 'UNVERIFIABLE' : 'NO_ORDER_NO';
    if (x.orderNo) {
      var k = known[x.orderNo];
      if (!k) return 'UNKNOWN_ORDER_NO';
      if (k[1] && x.l4 && k[1] !== x.l4) return 'ORDER_NO_BELONGS_TO_OTHER_CUSTOMER';
      if (k[0] && x.ext && k[0] !== x.ext) return 'ORDER_NO_HAS_OTHER_EXT_ID';
      return 'REAL';
    }
    var c = x.ext ? (knownByExt[x.ext] || []).filter(function (e) { return !e.l4 || !x.l4 || e.l4 === x.l4; }) : [];
    return c.length ? 'REAL_BY_EXT_ID(sheet mark missing)' : 'NO_ORDER_NO';
  }
  recs.forEach(function (x) { x.v = verdict(x); x.real = x.v === 'REAL' || x.v.indexOf('REAL_BY_EXT') === 0; });

  // ---- 1. repeated external order ids -------------------------------------------
  var byExt = {}; recs.forEach(function (x) { if (x.ext) (byExt[x.ext] = byExt[x.ext] || []).push(x); });
  var repeated = Object.keys(byExt).filter(function (k) { return byExt[k].length > 1; });
  log('');
  log('--- 1. REPEATED EXTERNAL ORDER IDs: ' + repeated.length + ' ids ---');
  var collisionIds = 0, sameLeadIds = 0, multiLineIds = 0, collisionRows = [];
  repeated.forEach(function (id) {
    var g = byExt[id];
    var pks = {}, skus = {}; g.forEach(function (x) { pks[x.pk || '-'] = 1; skus[x.sku || '-'] = 1; });
    var kind = Object.keys(pks).length > 1 ? 'DIFFERENT_LEADS_SHARE_ID' : (Object.keys(skus).length > 1 ? 'SAME_CUSTOMER_MULTI_LINE' : 'SAME_LEAD_REPEATED');
    if (kind === 'DIFFERENT_LEADS_SHARE_ID') { collisionIds++; g.forEach(function (x) { collisionRows.push(x.row); }); }
    else if (kind === 'SAME_LEAD_REPEATED') sameLeadIds++; else multiLineIds++;
    var owner = (knownByExt[id] || []).map(function (e) { return e.l4; });
    log('  id ' + id + ' [' + kind + '] ' + g.map(function (x) {
      var haveL4 = owner.some(function (o) { return o; });
      var tag = known && (knownByExt[id] || []).length ? (!haveL4 ? ' (owner unverified: use DIGESTS)' : (owner.indexOf(x.l4) >= 0 ? ' OWNER' : ' ORPHAN(no own order)')) : '';
      return 'row ' + x.row + ':' + (x.st || '-') + ':' + (x.orderNo || '-') + tag;
    }).join(' ; '));
  });
  log('  summary: DIFFERENT_LEADS_SHARE_ID=' + collisionIds + ' | SAME_CUSTOMER_MULTI_LINE=' + multiLineIds + ' | SAME_LEAD_REPEATED=' + sameLeadIds);

  // ---- 2. different leads sharing the same CODOPS order number ------------------
  var byNo = {}; recs.forEach(function (x) { if (x.orderNo) (byNo[x.orderNo] = byNo[x.orderNo] || []).push(x); });
  var sharedNos = Object.keys(byNo).filter(function (k) { var pk = {}; byNo[k].forEach(function (x) { pk[x.pk || '-'] = 1; }); return byNo[k].length > 1 && Object.keys(pk).length > 1; });
  var sharedAll = Object.keys(byNo).filter(function (k) { return byNo[k].length > 1; });
  log('');
  log('--- 2. DIFFERENT LEADS SHARING ONE CODOPS ORDER NUMBER: ' + sharedNos.length + ' order numbers (' + (sharedAll.length - sharedNos.length) + ' more shared by rows of the SAME customer) ---');
  var orphanFromShared = [];
  sharedNos.forEach(function (no) {
    var g = byNo[no], k = known ? known[no] : null;
    log('  ' + no + ' -> ' + g.map(function (x) {
      var tag = k && k[1] ? (k[1] === x.l4 ? 'OWNER' : 'ORPHAN') : '?';
      if (tag === 'ORPHAN') orphanFromShared.push(x.row);
      return 'row ' + x.row + '(ext ' + (x.ext || '-') + ',' + (x.st || '-') + ',' + tag + ')';
    }).join(' ; '));
  });

  // ---- classification of every row ----------------------------------------------
  function classify(x) {
    if (!x.hasName || !x.hasPhone) return 'SILENTLY_SKIPPED_NO_NAME_OR_PHONE';
    if (x.real) return 'OK';
    var marked = (x.st === 'IMPORTED' || x.st === 'DUPLICATE');
    if (marked && known) return 'FALSE_IMPORTED';
    if (marked) return 'IMPORTED_UNVERIFIED';
    if (x.st === 'REJECTED' || x.st === 'ERROR') return 'REJECTED_OR_ERROR';
    return 'NEVER_IMPORTED(status ' + (x.st || 'blank') + ')';
  }
  recs.forEach(function (x) { x.cls = classify(x); });

  // ---- 3. IMPORTED without a matching real CODOPS order -------------------------
  var fi = recs.filter(function (x) { return x.cls === 'FALSE_IMPORTED' || (x.cls === 'SILENTLY_SKIPPED_NO_NAME_OR_PHONE' && (x.st === 'IMPORTED' || x.st === 'DUPLICATE') && !x.real); });
  log('');
  log('--- 3. ROWS MARKED IMPORTED/DUPLICATE WITHOUT A MATCHING REAL CODOPS ORDER: ' + fi.length + (known ? '' : ' (reference data not loaded: only rows with no order number can be detected)') + ' ---');
  var reasons = {};
  fi.forEach(function (x) { (reasons[x.v] = reasons[x.v] || []).push(x.row); });
  Object.keys(reasons).forEach(function (k) { log('  ' + k + ': ' + reasons[k].length + ' rows -> ' + cap(reasons[k], 60)); });

  // ---- 7. same phone, several orders --------------------------------------------
  var byPhone = {}; recs.forEach(function (x) { if (x.pk.length >= 8) (byPhone[x.pk] = byPhone[x.pk] || []).push(x); });
  var legit = 0, likelyDup = 0, legitSamples = [], dupSamples = [];
  Object.keys(byPhone).forEach(function (p) {
    var g = byPhone[p]; if (g.length < 2) return;
    var keys = {}; g.forEach(function (x) { keys[[x.ext, x.sku, x.qty, x.total, x.date].join('|')] = 1; });
    if (Object.keys(keys).length > 1) { legit++; if (legitSamples.length < 15) legitSamples.push(g.map(function (x) { return x.row; }).join('/')); }
    else { likelyDup++; if (dupSamples.length < 15) dupSamples.push(g.map(function (x) { return x.row; }).join('/')); }
  });
  log('');
  log('--- 7. SAME PHONE ON SEVERAL ROWS (phone alone is NOT treated as duplication) ---');
  log('  groups with DIFFERENT order id/SKU/qty/total/date (legitimate distinct orders): ' + legit + (legitSamples.length ? ' e.g. rows ' + legitSamples.join(' ; ') : ''));
  log('  groups with IDENTICAL order id+SKU+qty+total+date (likely true duplicate rows): ' + likelyDup + (dupSamples.length ? ' e.g. rows ' + dupSamples.join(' ; ') : ''));

  // ---- 4. missing leads per day -------------------------------------------------
  // exact day from the date column; otherwise estimated from the nearest previous verified order (import day).
  var anchorDay = '', nextDays = [], i;
  for (i = recs.length - 1; i >= 0; i--) { nextDays[i] = anchorDay; if (recs[i].real && known) { var kk = known[recs[i].orderNo] || null; if (kk) anchorDay = kk[3]; } }
  var prevDay = '';
  recs.forEach(function (x, idx) {
    if (x.real && known && known[x.orderNo]) prevDay = known[x.orderNo][3];
    if (x.date) { x.day = x.date; x.exact = true; }
    else { var a = prevDay, b = nextDays[idx]; x.day = a && b && a !== b ? a + '..' + b : (a || b || 'unknown'); x.exact = false; }
  });
  var missing = recs.filter(function (x) { return x.cls !== 'OK' && x.cls !== 'IMPORTED_UNVERIFIED'; });
  log('');
  log('--- 4. MISSING LEADS (rows with name+phone that have NO real CODOPS order), grouped by day ---');
  log('  (' + (recs.some(function (x) { return x.exact; }) ? 'exact where the sheet has a date; otherwise "a..b" = between verified orders imported on a and b' : 'no date column: day = import day window between verified neighbouring orders') + ')');
  var dayMap = {};
  missing.forEach(function (x) { var d = dayMap[x.day] = dayMap[x.day] || { rows: [], cls: {} }; d.rows.push(x.row); d.cls[x.cls] = (d.cls[x.cls] || 0) + 1; });
  Object.keys(dayMap).sort().forEach(function (d) {
    var inScope = DAYS.some(function (t) { return d.indexOf(t) >= 0; });
    log('  ' + d + (inScope ? '  <== IN SCOPE' : '') + ': ' + dayMap[d].rows.length + ' rows | ' + Object.keys(dayMap[d].cls).map(function (c) { return c + '=' + dayMap[d].cls[c]; }).join(', '));
    if (inScope) log('      rows ' + cap(dayMap[d].rows, 80));
  });

  // ---- 5. incorrectly skipped leads ---------------------------------------------
  var skippedSilently = recs.filter(function (x) { return x.cls === 'SILENTLY_SKIPPED_NO_NAME_OR_PHONE'; });
  var rejected = recs.filter(function (x) { return x.cls === 'REJECTED_OR_ERROR'; });
  var never = recs.filter(function (x) { return x.cls.indexOf('NEVER_IMPORTED') === 0; });
  log('');
  log('--- 5. LEADS THE IMPORTER SKIPPED OR NEVER IMPORTED ---');
  log('  silently skipped (missing name/phone): ' + skippedSilently.length + (skippedSilently.length ? ' rows ' + cap(skippedSilently.map(function (x) { return x.row; }), 60) : ''));
  log('  rejected/error (see column ' + (col.error >= 0 ? letter(col.error) : '?') + '): ' + rejected.length + (rejected.length ? ' rows ' + cap(rejected.map(function (x) { return x.row; }), 60) : ''));
  var errTypes = {}; rejected.forEach(function (x) { var e = x.err || '(no message)'; errTypes[e] = (errTypes[e] || 0) + 1; });
  Object.keys(errTypes).slice(0, 10).forEach(function (e) { log('      "' + e + '" x' + errTypes[e]); });
  log('  never imported (blank/other status): ' + never.length + (never.length ? ' rows ' + cap(never.map(function (x) { return x.row; }), 60) : ''));
  log('  falsely marked IMPORTED (see section 3): ' + fi.length);

  // ---- SKU check ----------------------------------------------------------------
  var skuCount = {}; recs.forEach(function (x) { var s = x.sku ? x.sku.toUpperCase() : '(empty)'; skuCount[s] = (skuCount[s] || 0) + 1; });
  log('');
  log('--- SKU VALUES IN SHEET (' + (knownSkus ? 'CODOPS active SKUs: ' + knownSkus.join(', ') : 'CODOPS SKU list not loaded') + ') ---');
  Object.keys(skuCount).sort(function (a, b) { return skuCount[b] - skuCount[a]; }).slice(0, 20).forEach(function (s) {
    log('  ' + s + ': ' + skuCount[s] + ((knownSkus && s !== '(empty)' && knownSkus.indexOf(s) < 0) ? '  <== NOT A CODOPS PRODUCT (would be rejected)' : (s === '(empty)' ? '  <== EMPTY (would be rejected)' : '')));
  });

  // ---- per-day status table + totals --------------------------------------------
  log('');
  log('--- STATUS COUNTS PER DAY IN SCOPE (exact date column only) ---');
  DAYS.forEach(function (d) {
    var g = recs.filter(function (x) { return x.exact && x.date === d; }), c = {};
    g.forEach(function (x) { var k = x.st || 'BLANK'; c[k] = (c[k] || 0) + 1; });
    log('  ' + d + ': rows=' + g.length + ' | ' + Object.keys(c).map(function (k) { return k + '=' + c[k]; }).join(' ') + ' | real orders=' + g.filter(function (x) { return x.real; }).length);
  });
  var okRows = recs.filter(function (x) { return x.cls === 'OK'; }).length;
  log('');
  log('=== TOTALS: sheet rows ' + recs.length + ' | with real CODOPS order ' + okRows + ' | missing ' + missing.length + ' | silently skipped ' + skippedSilently.length + ' | collision-affected rows ' + collisionRows.length + ' ===');
  if (known) {
    var seen = {}; recs.forEach(function (x) { if (x.real && x.orderNo) seen[x.orderNo] = 1; });
    log('CODOPS orders (GOOGLE_SHEETS) not matched by any row of this tab: ' + (Object.keys(known).length - Object.keys(seen).length) + ' (other feeds/spreadsheets or rows later removed)');
  }
  // ---- ROW DIGESTS: lets CODOPS verify each row server-side WITHOUT any phone number leaving the sheet ----
  // digest = first 12 hex of HMAC-SHA256(DIAG_KEY, last 9 digits of the phone). Without the key it cannot be reversed.
  log('');
  if (typeof DIAG_KEY === 'undefined') {
    log('--- ROW DIGESTS: skipped (DIAG_KEY not defined; paste codops_known_orders.gs to enable server-side verification) ---');
  } else {
    log('--- ROW DIGESTS (copy everything between the markers back to CODOPS support) ---');
    log('DIGESTS_BEGIN');
    log('row|ext|status|orderNo|sku|qty|total|digest');
    recs.forEach(function (x) {
      if (!x.hasPhone) { log([x.row, x.ext, x.st, x.orderNo, x.sku, x.qty, x.total, 'NOPHONE'].join('|')); return; }
      var sig = Utilities.computeHmacSha256Signature(x.pk, DIAG_KEY);
      var hex = sig.map(function (b) { return ('0' + (b < 0 ? b + 256 : b).toString(16)).slice(-2); }).join('').slice(0, 12);
      log([x.row, x.ext, x.st, x.orderNo, x.sku, x.qty, x.total, hex].join('|'));
    });
    log('DIGESTS_END');
  }
  log('=== end: nothing was sent, written or modified ===');
  var text = out.join('\n');
  for (var p = 0; p < text.length; p += 7000) Logger.log(text.substring(p, p + 7000));
}


/**
 * READ-ONLY inventory of this Apps Script project's triggers. Run it in EVERY copy of the lead spreadsheet.
 * Prints which spreadsheet this is (md5 prefix, matches the masked ids CODOPS reports), the webhook target host,
 * a token fingerprint (never the token) and every installed trigger. Changes nothing.
 * Account-wide view of all projects: https://script.google.com/home/triggers
 */
function listCallCenterTriggers() {
  var out = [];
  function hex(bytes) { return bytes.map(function (b) { return ('0' + (b < 0 ? b + 256 : b).toString(16)).slice(-2); }).join(''); }
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  out.push('Spreadsheet: "' + ss.getName() + '" | id-hash ' + hex(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, ss.getId())).slice(0, 6));
  out.push('Tabs: ' + ss.getSheets().map(function (s) { return '"' + s.getName() + '"(' + Math.max(s.getLastRow() - 1, 0) + ')'; }).join(', '));
  var hook = (typeof CALL_CENTER_WEBHOOK !== 'undefined') ? CALL_CENTER_WEBHOOK : null;
  out.push('CALL_CENTER_WEBHOOK: ' + (hook ? hook.replace(/\?.*$/, '').replace(/^(https?:\/\/[^\/]+\/api\/v1\/integrations\/google-sheets\/)(.{6}).*(\/webhook)$/, '$1$2...$3') + (/[?&]token=/.test(hook) ? '  (token embedded in URL)' : '') : '(not defined in this project)'));
  var tok = (typeof CALL_CENTER_TOKEN !== 'undefined') ? CALL_CENTER_TOKEN : (hook && hook.match(/token=([^&]+)/) ? hook.match(/token=([^&]+)/)[1] : null);
  out.push('Token fingerprint: ' + (tok ? hex(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, tok)).slice(0, 8) : '(none found)'));
  out.push('SOURCE_SHEET_NAME: ' + ((typeof SOURCE_SHEET_NAME !== 'undefined') ? '"' + SOURCE_SHEET_NAME + '"' : '(not defined)'));
  var triggers = ScriptApp.getProjectTriggers();
  out.push('Installed triggers: ' + triggers.length);
  triggers.forEach(function (t) {
    out.push('  - handler ' + t.getHandlerFunction() + ' | type ' + t.getEventType() + ' | source ' + t.getTriggerSource() + ' | id ' + t.getUniqueId());
  });
  out.push('Nothing was changed.');
  Logger.log(out.join('\n'));
}
