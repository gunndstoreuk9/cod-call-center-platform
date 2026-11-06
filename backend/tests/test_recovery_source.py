"""GOOGLE_SHEETS_RECOVERY: recovered leads are real, visible, unassigned orders that do NOT count as new acquisition."""
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.db import SessionLocal
from app.core.sources import RECOVERY_SOURCE
from app.core.time import utcnow
from app.models import IntegrationEvent, Order, OrderAssignment
from scripts.recover_leads import run_recovery


def _setup(client, sku):
    store = client.get('/api/v1/stores').json()[0]
    r = client.post('/api/v1/products', json={'store_id': store['id'], 'name': sku, 'sku': sku, 'selling_price': 199, 'currency': 'MAD', 'commission_per_confirmation': 5, 'offers': []})
    assert r.status_code == 200, r.text
    # run_recovery targets the single GOOGLE_SHEETS integration of the database, so reuse/create exactly one
    integ = client.post('/api/v1/integrations', json={'provider': 'GOOGLE_SHEETS', 'name': 'Rec', 'store_id': store['id'], 'config': {'sheet_name': 'orders', 'auto_assign': True}, 'secrets': {}}).json()
    script = client.get(f"/api/v1/integrations/google-sheets/{integ['id']}/script").json()
    token = parse_qs(urlparse(script['webhook_url']).query)['token'][0]
    return integ, token


def _items(sku, n, tag, start_row=10):
    return [{'sheet': 'A', 'row_number': start_row + i, 'sku': sku, 'customer_name': f'Rec {tag}{i}', 'phone': f'069{tag}{i:05d}'[:10], 'city': 'Fes', 'quantity': 2, 'total_price': 249, 'external_order_id': f'REC-{tag}-1',
             'source': {'spreadsheet_id': '1XVymbRmiVVWLnLc2TrpOfOY6W5H2ZWCnHiDzStXxy_A', 'tab': 'orders'}} for i in range(n)]


def _kpi(client):
    o = client.get('/api/v1/analytics/overview?range=today').json()
    p = next(x for x in client.get('/api/v1/analytics/products?range=today').json() if x['recovered_leads'] >= 0)
    return o


def test_recovery_import_semantics_idempotency_and_webhook_cannot_forge_it(client):
    integ, token = _setup(client, 'REC-SKU-1')
    items = _items('REC-SKU-1', 3, '11')              # same external id for 3 different customers => collision-derived ids
    db = SessionLocal()
    dry = run_recovery(db, items, 'B1', apply=False, integration_id=integ['id'])
    assert dry['counts'] == {'INSERTED': 3} and dry['orders_before'] == dry['orders_after'] and dry['existing_rows_untouched']
    with SessionLocal() as chk: assert chk.query(Order).filter(Order.source == RECOVERY_SOURCE).count() == 0   # dry run kept nothing

    res = run_recovery(db, items, 'B1', apply=True, integration_id=integ['id'])
    assert res['counts'] == {'INSERTED': 3}
    with SessionLocal() as chk:
        rows = chk.query(Order).filter(Order.source == RECOVERY_SOURCE).all()
        assert len(rows) == 3
        for o in rows:
            assert o.call_status == 'NEW' and o.assigned_agent_id is None and o.assigned_at is None
            assert o.quantity == 2 and float(o.total_price) == 249.0 and 'original submission date unknown' in o.call_note
            assert chk.query(OrderAssignment).filter(OrderAssignment.order_id == o.id).count() == 0
            ev = chk.query(IntegrationEvent).filter(IntegrationEvent.entity_id == o.id, IntegrationEvent.status == 'SUCCESS').one()
            assert ev.payload['recovery'] is True and ev.payload['recovered_at'] and ev.payload['source']['submitted_at'] == 'unknown'
            assert ev.payload['source']['spreadsheet_id'].startswith('1XVymbRm') and ev.payload['source']['row'] >= 10 and ev.payload['source']['recovery_batch'] == 'B1'
            assert (utcnow() - o.created_at.replace(tzinfo=utcnow().tzinfo)).total_seconds() < 600     # created_at = real recovery time, not backdated
    # retry the same recovery: no duplicates, nothing changes
    again = run_recovery(db, items, 'B1', apply=True, integration_id=integ['id'])
    assert again['counts'] == {'DUPLICATE': 3} and again['orders_after'] == res['orders_after']
    # the normal webhook later sending the same leads must not create duplicates either
    url = f"/api/v1/integrations/google-sheets/{integ['id']}/webhook"
    web = client.post(url, json={'orders': [{k: v for k, v in i.items() if k in ('row_number', 'sku', 'customer_name', 'phone', 'city', 'quantity', 'total_price', 'external_order_id')} for i in items]}, headers={'X-Webhook-Token': token}).json()
    assert [r['outcome'] for r in web['results']] == ['DUPLICATE'] * 3
    # the webhook can never mint recovery orders, even if a client tries
    forged = {**{k: v for k, v in items[0].items() if k in ('row_number', 'sku', 'customer_name', 'phone', 'city', 'quantity', 'total_price')}, 'external_order_id': 'REC-FORGED', 'phone': '0690000999', 'recovery': True, 'source': RECOVERY_SOURCE}
    r = client.post(url, json={'orders': [forged]}, headers={'X-Webhook-Token': token}).json()['results'][0]
    assert r['outcome'] == 'INSERTED'
    with SessionLocal() as chk: assert chk.query(Order).filter(Order.external_order_id == 'REC-FORGED').one().source == 'GOOGLE_SHEETS'
    db.close()


def test_acquisition_kpis_exclude_recovery_but_workload_and_revenue_include_it(client):
    integ, token = _setup(client, 'REC-SKU-2')
    before = client.get('/api/v1/analytics/overview?range=today').json()
    bprod = {x['sku']: x for x in client.get('/api/v1/analytics/products?range=today').json()}
    db = SessionLocal()
    run_recovery(db, _items('REC-SKU-2', 4, '22', 40), 'B2', apply=True, integration_id=integ['id'])
    after = client.get('/api/v1/analytics/overview?range=today').json()
    # acquisition KPIs unchanged
    for k in ('leads', 'called', 'confirmed', 'confirmation_rate', 'no_answer', 'cancelled', 'dispatched', 'delivered'):
        assert after[k] == before[k], k
    # separate counter + operational workload
    assert after['recovered_leads'] == before['recovered_leads'] + 4 and after['recovered_unassigned'] == before['recovered_unassigned'] + 4
    assert after['unassigned'] == before['unassigned'] + 4
    # still fully listed in the Orders page
    page = client.get('/api/v1/orders/paginated?limit=100&offset=0&search=Rec 22').json()
    names = page['items'] if isinstance(page, dict) and 'items' in page else page
    assert (page['total'] if isinstance(page, dict) and 'total' in page else len(names)) >= 4
    # confirm + deliver one recovered order: revenue counts it once, acquisition counts still ignore it
    with SessionLocal() as s:
        o = s.query(Order).filter(Order.source == RECOVERY_SOURCE, Order.call_status == 'NEW').order_by(Order.created_at.desc()).first()
        o.call_status = 'CONFIRMED'; o.confirmed_at = utcnow(); o.delivery_status = 'DELIVERED'; o.delivered_at = utcnow()
        s.commit()
    fin = client.get('/api/v1/analytics/overview?range=today').json()
    assert fin['confirmed'] == before['confirmed'] and fin['delivered'] == before['delivered'] and fin['confirmation_rate'] == before['confirmation_rate']
    assert fin['recovered_confirmed'] == before['recovered_confirmed'] + 1
    assert float(fin['confirmed_revenue']) == float(before['confirmed_revenue']) + 249.0
    assert float(fin['delivered_revenue']) == float(before['delivered_revenue']) + 249.0
    prod = {x['sku']: x for x in client.get('/api/v1/analytics/products?range=today').json()}['REC-SKU-2']
    assert prod['leads'] == 0 and prod['confirmed'] == 0 and prod['recovered_leads'] == 4 and float(prod['delivered_revenue']) == 249.0
    # sync-status: acquisition feed stats untouched, recovered tracked separately
    st = client.get(f"/api/v1/integrations/google-sheets/{integ['id']}/sync-status").json()
    assert st['recovered_leads_total'] >= 4
    db.close()


def test_profit_cpa_ignores_recovered_confirmations_but_revenue_counts_them(client):
    integ, token = _setup(client, 'REC-SKU-3')
    before = client.get('/api/v1/profit/dashboard?range=today').json()
    db = SessionLocal()
    run_recovery(db, _items('REC-SKU-3', 2, '33', 70), 'B3', apply=True, integration_id=integ['id'])
    with SessionLocal() as s:
        for o in s.query(Order).filter(Order.external_order_id.like('REC-33-1%'), Order.source == RECOVERY_SOURCE).all():
            o.call_status = 'CONFIRMED'; o.confirmed_at = utcnow(); o.delivery_status = 'DELIVERED'; o.delivered_at = utcnow()
        s.commit()
    after = client.get('/api/v1/profit/dashboard?range=today').json()
    assert after['leads'] == before['leads'] and after['confirmed'] == before['confirmed']          # acquisition counts / CPA denominators
    assert after['cpa_confirmed'] == before['cpa_confirmed']
    assert after['recovered_leads'] == before['recovered_leads'] + 2 and after['recovered_confirmed'] == before['recovered_confirmed'] + 2 and after['recovered_delivered'] == before['recovered_delivered'] + 2
    assert float(after['revenue']) == float(before['revenue']) + 2 * 249.0                          # real money counted once
    assert after['delivered'] == before['delivered'] + 2                                           # AOV stays consistent with revenue
    db.close()


def test_normal_import_unaffected_by_recovery_source(client):
    integ, token = _setup(client, 'REC-SKU-4')
    url = f"/api/v1/integrations/google-sheets/{integ['id']}/webhook"
    b = client.get('/api/v1/analytics/overview?range=today').json()
    r = client.post(url, json={'orders': [{'row_number': 5, 'sku': 'REC-SKU-4', 'customer_name': 'Normal', 'phone': '0691000001', 'external_order_id': 'norm-1'}]}, headers={'X-Webhook-Token': token}).json()['results'][0]
    assert r['outcome'] == 'INSERTED'
    a = client.get('/api/v1/analytics/overview?range=today').json()
    assert a['leads'] == b['leads'] + 1 and a['recovered_leads'] == b['recovered_leads']
    with SessionLocal() as s: assert s.query(Order).filter(Order.external_order_id == 'norm-1').one().source == 'GOOGLE_SHEETS'


def test_recovery_tool_guard_rails(client):
    integ, token = _setup(client, 'REC-SKU-5')
    db = SessionLocal()
    bad = _items('REC-SKU-5', 1, '55', 90); bad[0]['sku'] = ''
    with pytest.raises(SystemExit): run_recovery(db, bad, 'B5', apply=False, integration_id=integ['id'])          # empty SKU refused
    nosrc = _items('REC-SKU-5', 1, '56', 91); nosrc[0]['source'] = {}
    with pytest.raises(SystemExit): run_recovery(db, nosrc, 'B5', apply=False, integration_id=integ['id'])        # provenance required
    with pytest.raises(SystemExit): run_recovery(db, [], 'B5', apply=False, integration_id=integ['id'])
    db.close()


def test_concurrency_lock_contention_is_a_retryable_failure_and_normal_and_recovery_share_one_lock_key(client, monkeypatch):
    from app.services import google_sheets as gs
    integ, token = _setup(client, 'REC-SKU-6')
    url = f"/api/v1/integrations/google-sheets/{integ['id']}/webhook"
    keys = []
    real = gs._try_lock
    monkeypatch.setattr(gs, '_try_lock', lambda db, key: (keys.append(key), real(db, key))[1])
    item = {'row_number': 12, 'sku': 'REC-SKU-6', 'customer_name': 'Lock A', 'phone': '0692000001', 'city': 'Fes', 'quantity': 1, 'total_price': 199, 'external_order_id': 'LOCK-1'}
    db = SessionLocal()
    run_recovery(db, [{**item, 'sheet': 'A', 'source': {'spreadsheet_id': 'X' * 44, 'tab': 'orders'}}], 'B6', apply=False, integration_id=integ['id'])
    client.post(url, json={'orders': [item]}, headers={'X-Webhook-Token': token})
    assert len(keys) >= 2 and keys[0] == keys[1], keys                    # same identity => same advisory lock, whichever path imports it
    # blank-id leads: both paths lock on the same fingerprint
    keys.clear()
    blank = {**item, 'external_order_id': '', 'phone': '0692000002'}
    run_recovery(db, [{**blank, 'sheet': 'B', 'source': {'spreadsheet_id': 'Y' * 44, 'tab': 'orders'}}], 'B6', apply=False, integration_id=integ['id'])
    client.post(url, json={'orders': [blank]}, headers={'X-Webhook-Token': token})
    assert keys[0] == keys[1], keys
    # contention: another transaction holds the lead => nothing inserted, reported as a transient (retryable) FAILED
    monkeypatch.setattr(gs, '_try_lock', lambda db, key: False)
    before = SessionLocal().query(Order).count()
    r = client.post(url, json={'orders': [{**item, 'external_order_id': 'LOCK-2', 'phone': '0692000003'}]}, headers={'X-Webhook-Token': token}).json()
    assert r['results'][0]['outcome'] == 'FAILED' and 'concurrent' in r['results'][0]['error'].lower() and r['summary']['transient_failed'] == 1 and r['summary']['rejected'] == 0
    assert SessionLocal().query(Order).count() == before
    res = run_recovery(db, [{**item, 'external_order_id': 'LOCK-3', 'phone': '0692000004', 'sheet': 'A', 'source': {'spreadsheet_id': 'X' * 44, 'tab': 'orders'}}], 'B6', apply=True, integration_id=integ['id'])
    assert res['counts'] == {'FAILED': 1} and res['inserted'] == 0
    db.close()


def test_recovery_never_modifies_an_existing_customer_and_probe_reports_dashboard(client):
    from app.models import Customer
    integ, token = _setup(client, 'REC-SKU-7')
    url = f"/api/v1/integrations/google-sheets/{integ['id']}/webhook"
    client.post(url, json={'orders': [{'row_number': 3, 'sku': 'REC-SKU-7', 'customer_name': 'Original Name', 'phone': '0693000001', 'city': 'Rabat', 'address': 'Original address', 'external_order_id': 'CUST-1'}]}, headers={'X-Webhook-Token': token})
    with SessionLocal() as s:
        c = s.query(Customer).filter(Customer.phone_e164 == '+212693000001').one(); snap = (c.name, c.city, c.address)
    db = SessionLocal()
    it = {'sheet': 'A', 'row_number': 20, 'sku': 'REC-SKU-7', 'customer_name': 'Different Name', 'phone': '0693000001', 'city': 'Tangier', 'address': 'New address', 'quantity': 1, 'total_price': 199, 'external_order_id': 'CUST-2',
          'source': {'spreadsheet_id': 'Z' * 44, 'tab': 'orders'}}
    res = run_recovery(db, [it], 'B7', apply=True, integration_id=integ['id'], probe=True)
    assert res['counts'] == {'INSERTED': 1}
    with SessionLocal() as s:
        c = s.query(Customer).filter(Customer.phone_e164 == '+212693000001').one()
        assert (c.name, c.city, c.address) == snap                                        # customer record untouched
    pb, pa = res['dashboard_before'], res['dashboard_after_inside_transaction']
    assert pa['overview']['leads'] == pb['overview']['leads'] and pa['overview']['recovered_leads'] == pb['overview']['recovered_leads'] + 1
    assert pa['profit']['leads'] == pb['profit']['leads'] and pa['profit']['recovered_leads'] == pb['profit']['recovered_leads'] + 1
    db.close()


def test_revenue_and_count_populations_are_explicit_in_the_api(client):
    o = client.get('/api/v1/analytics/overview?range=today').json()
    assert o['kpi_population'] == {'counts_and_rates': 'acquisition_only', 'revenue': 'all_orders_incl_recovered', 'workload_assigned_unassigned': 'all_orders_incl_recovered'}
    assert float(o['confirmed_revenue']) == float(o['confirmed_revenue_acquisition']) + float(o['confirmed_revenue_recovered'])
    p = client.get('/api/v1/profit/dashboard?range=today').json()
    assert p['kpi_population']['leads_confirmed_cpa'] == 'acquisition_only' and 'revenue_recovered' in p


def test_resend_after_quantity_total_alias_fix_is_still_a_duplicate(client):
    """Orders imported by the old script (quantity 1, no total) must be recognised when V2 re-sends the same lead with real values."""
    integ, token = _setup(client, 'REC-SKU-8')
    url = f"/api/v1/integrations/google-sheets/{integ['id']}/webhook"
    post = lambda o: client.post(url, json={'orders': [o]}, headers={'X-Webhook-Token': token}).json()['results'][0]
    # 1) blank-id lead (Sheet-2 shape)
    old = {'row_number': 4, 'sku': 'REC-SKU-8', 'customer_name': 'Alias Fix', 'phone': '0694000001', 'city': 'Fes'}                      # old script: qty 1, no total
    assert post(old)['outcome'] == 'INSERTED'
    new = {**old, 'quantity': 2, 'total_price': 249}                                                                                    # V2: real values
    assert post(new)['outcome'] == 'DUPLICATE'
    # 2) id-collision lead (Sheet-1 shape): two customers share an id, imported by the old script
    a = {'row_number': 5, 'sku': 'REC-SKU-8', 'customer_name': 'First', 'phone': '0694000002', 'external_order_id': 'AF-1'}
    b = {'row_number': 6, 'sku': 'REC-SKU-8', 'customer_name': 'Second', 'phone': '0694000003', 'external_order_id': 'AF-1'}
    assert post(a)['outcome'] == 'INSERTED' and post(b)['outcome'] == 'INSERTED' and post(b)['outcome'] == 'DUPLICATE'
    assert post({**a, 'quantity': 3, 'total_price': 299})['outcome'] == 'DUPLICATE'
    assert post({**b, 'quantity': 3, 'total_price': 299})['outcome'] == 'DUPLICATE'      # corrected values must NOT mint a new derived id
    with SessionLocal() as s:
        assert s.query(Order).filter(Order.external_order_id.like('AF-1%')).count() == 2
        assert s.query(Order).filter(Order.customer_id == s.query(Order.customer_id).filter(Order.external_order_id == 'AF-1').scalar()).count() == 1
    # 3) a genuinely different lead (other customer / other SKU) is still imported
    assert post({**b, 'phone': '0694000009', 'customer_name': 'Third'})['outcome'] == 'INSERTED'


def test_sync_status_feed_liveness_heartbeat_and_expected_feeds_with_legacy_noise(client):
    from datetime import timedelta
    from app.models import IntegrationEvent
    integ, token = _setup(client, 'REC-SKU-9')
    url = f"/api/v1/integrations/google-sheets/{integ['id']}/sync-status"
    with SessionLocal() as s:
        # lots of legacy-script batches (no feed identity) must not hide the v2 feeds (old code loaded only the oldest 5000 rows)
        for i in range(60):
            s.add(IntegrationEvent(integration_id=integ['id'], provider='GOOGLE_SHEETS', direction='INBOUND', event_type='BATCH_SUMMARY', status='FAILED', payload={'received': 267, 'inserted': 0, 'rejected': 267}, created_at=utcnow() - timedelta(days=6, minutes=i)))
        s.add(IntegrationEvent(integration_id=integ['id'], provider='GOOGLE_SHEETS', direction='INBOUND', event_type='BATCH_SUMMARY', status='SUCCESS', payload={'received': 0, 'inserted': 0, 'rejected': 0, 'client': {'spreadsheet': 'b1819f', 'tab': 'gid 1', 'version': 'v2'}}, created_at=utcnow() - timedelta(minutes=5)))
        s.add(IntegrationEvent(integration_id=integ['id'], provider='GOOGLE_SHEETS', direction='INBOUND', event_type='BATCH_SUMMARY', status='SUCCESS', payload={'received': 0, 'inserted': 0, 'rejected': 0, 'client': {'spreadsheet': '66800c', 'tab': 'gid 2', 'version': 'v2'}}, created_at=utcnow() - timedelta(minutes=200)))
        s.commit()
    st = client.get(url + '?expect=b1819f,66800c,ffffff').json()
    assert 'b1819f/gid 1' in st['feeds_last_7_days'] and st['feeds_last_7_days']['b1819f/gid 1']['version'] == 'v2'
    assert not any('b1819f' in a and 'no contact' in a for a in st['alerts'])                       # fresh heartbeat => healthy
    assert any('66800c' in a and 'no contact for' in a for a in st['alerts'])                         # 200 min silent => alert
    assert any('Expected feed ffffff has not contacted' in a for a in st['alerts'])                  # never seen


def test_monitor_cli_exit_semantics(client):
    from scripts.monitor_sync import check
    db = SessionLocal()
    out = check(db, None)                      # test DB has many integrations => monitor refuses to guess
    assert out['critical'] and 'exactly one' in out['error']
    db.close()
