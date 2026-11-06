from urllib.parse import urlparse, parse_qs


def test_google_sheets_integration_import_and_script(client):
    store = client.get('/api/v1/stores').json()[0]
    products = client.get('/api/v1/products?status=ACTIVE').json()
    product = next((p for p in products if p['sku'] == 'TEST-SKU-1'), None)
    if not product:
        r = client.post('/api/v1/products', json={
            'store_id': store['id'], 'name': 'Sheets Product', 'sku': 'SHEETS-SKU-1',
            'selling_price': 199, 'currency': 'MAD', 'commission_per_confirmation': 5, 'offers': []
        })
        assert r.status_code == 200
        product = r.json()

    r = client.post('/api/v1/integrations', json={
        'provider': 'GOOGLE_SHEETS', 'name': 'Lead Sheet', 'store_id': store['id'],
        'config': {'sheet_name': 'Leads', 'auto_assign': False}, 'secrets': {}
    })
    assert r.status_code == 200, r.text
    integration = r.json()
    assert integration['provider'] == 'GOOGLE_SHEETS'
    assert 'webhook_token' in integration['secret_keys']
    assert 'secrets_encrypted' not in integration

    script_r = client.get(f"/api/v1/integrations/google-sheets/{integration['id']}/script")
    assert script_r.status_code == 200, script_r.text
    script_data = script_r.json()
    assert 'sendNewLeadsToCallCenter' in script_data['script']
    assert 'installEveryMinuteTrigger' in script_data['script']
    token = parse_qs(urlparse(script_data['webhook_url']).query)['token'][0]

    hook = client.post(
        f"/api/v1/integrations/google-sheets/{integration['id']}/webhook?token={token}",
        json={'orders': [{
            'row_number': 2, 'sku': product['sku'].lower(), 'customer_name': 'Sheet Customer',
            'phone': '0612345678', 'city': 'Casablanca', 'quantity': 2, 'total_price': 350,
            'external_order_id': 'sheet-test-order-1'
        }]}
    )
    assert hook.status_code == 200, hook.text
    result = hook.json()['results'][0]
    assert result['status'] == 'IMPORTED'

    orders = client.get('/api/v1/orders?search=Sheet Customer').json()
    assert any(o['source'] == 'GOOGLE_SHEETS' and o['external_order_id'] == 'sheet-test-order-1' for o in orders)


def test_digylog_integration_secret_and_webhook_config(client):
    store = client.get('/api/v1/stores').json()[0]
    r = client.post('/api/v1/integrations', json={
        'provider': 'DIGYLOG', 'name': 'Digylog Test', 'store_id': store['id'],
        'config': {'network': 1, 'port': 1, 'add_status': 1},
        'secrets': {'api_token': 'private-test-token'}
    })
    assert r.status_code == 200, r.text
    integration = r.json()
    assert set(integration['secret_keys']) == {'api_token', 'webhook_token'}
    assert 'private-test-token' not in r.text

    w = client.get(f"/api/v1/integrations/{integration['id']}/webhook-config")
    assert w.status_code == 200
    assert '?token=' in w.json()['webhook_url']

    bad = client.post(f"/api/v1/integrations/digylog/{integration['id']}/webhook?token=wrong", json={'type': 'ping'})
    assert bad.status_code == 401


def test_digylog_live_delivery_event_and_dashboard(client):
    store = client.get('/api/v1/stores').json()[0]
    products = client.get('/api/v1/products?status=ACTIVE').json()
    product = products[0]
    order_r = client.post('/api/v1/orders/manual', json={
        'store_id': store['id'], 'product_id': product['id'], 'customer_name': 'Delivery Customer',
        'phone': '0630303030', 'city': 'Casablanca', 'call_status': 'CONFIRMED'
    })
    assert order_r.status_code == 200, order_r.text
    order = order_r.json()

    r = client.post('/api/v1/integrations', json={
        'provider': 'DIGYLOG', 'name': 'Digylog Live Test', 'store_id': store['id'],
        'config': {'network': 1, 'port': 1, 'add_status': 1},
        'secrets': {'api_token': 'private-test-token-2'}
    })
    assert r.status_code == 200, r.text
    integration = r.json()
    w = client.get(f"/api/v1/integrations/{integration['id']}/webhook-config").json()
    token = parse_qs(urlparse(w['webhook_url']).query)['token'][0]

    hook = client.post(
        f"/api/v1/integrations/digylog/{integration['id']}/webhook?token={token}",
        json={'type': 'order-status-changed', 'payload': {'num': order['order_number'], 'traking': 'DG-LIVE-001', 'idStatus': 6}}
    )
    assert hook.status_code == 200, hook.text
    assert hook.json()['delivery_status'] == 'DELIVERED'

    events = client.get(f"/api/v1/delivery/events?integration_id={integration['id']}").json()
    assert any(e['tracking_number'] == 'DG-LIVE-001' and e['internal_status'] == 'DELIVERED' and e['matched'] for e in events)

    shipments = client.get(f"/api/v1/delivery/shipments?integration_id={integration['id']}").json()
    assert any(s['tracking_number'] == 'DG-LIVE-001' and s['status'] == 'DELIVERED' and s['external_status_id'] == 6 for s in shipments)

    dashboard = client.get('/api/v1/delivery/dashboard?range=today').json()
    assert dashboard['delivered'] >= 1
    assert 'products' in dashboard and 'agents' in dashboard


def test_ozon_express_credentials_and_webhook(client):
    store = client.get('/api/v1/stores').json()[0]

    products = client.get('/api/v1/products?status=ACTIVE').json()
    product = next((p for p in products if p['sku'] == 'OZON-TEST-1'), None)

    if not product:
        product_r = client.post('/api/v1/products', json={
            'store_id': store['id'],
            'name': 'Ozon Test Product',
            'sku': 'OZON-TEST-1',
            'selling_price': 199,
            'currency': 'MAD',
            'commission_per_confirmation': 5,
            'offers': []
        })
        assert product_r.status_code == 200, product_r.text
        product = product_r.json()

    order_r = client.post('/api/v1/orders/manual', json={
        'store_id': store['id'], 'product_id': product['id'], 'customer_name': 'Ozon Customer',
        'phone': '0640404040', 'city': 'Rabat', 'call_status': 'CONFIRMED'
    })
    assert order_r.status_code == 200, order_r.text
    order = order_r.json()

    r = client.post('/api/v1/integrations', json={
        'provider': 'OZON_EXPRESS', 'name': 'Ozon Express Test', 'store_id': store['id'],
        'config': {
            'api_base_url': 'https://ozoneexpress.ma/api/',
            'create_parcel_url': 'https://ozoneexpress.ma/api/{client_id}/{api_key}/parcels',
            'auth_mode': 'path',
        },
        'secrets': {'client_id': '12345', 'api_key': 'private-ozon-key'},
    })
    assert r.status_code == 200, r.text
    integration = r.json()
    assert integration['provider'] == 'OZON_EXPRESS'
    assert set(integration['secret_keys']) == {'api_key', 'client_id', 'webhook_token'}
    assert 'private-ozon-key' not in r.text

    webhook = client.get(f"/api/v1/integrations/{integration['id']}/webhook-config")
    assert webhook.status_code == 200, webhook.text
    token = parse_qs(urlparse(webhook.json()['webhook_url']).query)['token'][0]

    bad = client.post(
        f"/api/v1/integrations/ozon-express/{integration['id']}/webhook?token=wrong",
        json={'reference': order['order_number'], 'parcel_code': 'OZ-001', 'status': 'DELIVERED'},
    )
    assert bad.status_code == 401

    hook = client.post(
        f"/api/v1/integrations/ozon-express/{integration['id']}/webhook?token={token}",
        json={'reference': order['order_number'], 'parcel_code': 'OZ-001', 'status': 'DELIVERED'},
    )
    assert hook.status_code == 200, hook.text
    assert hook.json()['matched'] is True
    assert hook.json()['delivery_status'] == 'DELIVERED'

    shipments = client.get(f"/api/v1/delivery/shipments?integration_id={integration['id']}").json()
    assert any(s['provider'] == 'OZON_EXPRESS' and s['tracking_number'] == 'OZ-001' and s['status'] == 'DELIVERED' for s in shipments)


def test_ozon_express_dispatch_builds_correct_payload_and_saves_tracking(client, monkeypatch):
    import json as _json
    import httpx

    store = client.get('/api/v1/stores').json()[0]

    products = client.get('/api/v1/products?status=ACTIVE').json()
    product = next((p for p in products if p['sku'] == 'OZON-DISPATCH-1'), None)

    if not product:
        product_r = client.post('/api/v1/products', json={
            'store_id': store['id'],
            'name': 'Ozon Dispatch Product',
            'sku': 'OZON-DISPATCH-1',
            'selling_price': 199,
            'currency': 'MAD',
            'commission_per_confirmation': 5,
            'offers': []
        })
        assert product_r.status_code == 200, product_r.text
        product = product_r.json()

    order_r = client.post('/api/v1/orders/manual', json={
        'store_id': store['id'],
        'product_id': product['id'],
        'customer_name': 'Mohammed Alami',
        'phone': '0612345678',
        'city': 'Casablanca',
        'address': '123 Rue Hassan II',
        'quantity': 2,
        'call_status': 'CONFIRMED',
    })
    assert order_r.status_code == 200, order_r.text
    order = order_r.json()

    integration_r = client.post('/api/v1/integrations', json={
        'provider': 'OZON_EXPRESS',
        'name': 'Ozon Express Dispatch Test',
        'store_id': store['id'],
        'config': {
            'api_base_url': 'https://api.ozonexpress.ma',
            'create_parcel_url': 'https://api.ozonexpress.ma/customers/{client_id}/{api_key}/add-parcel',
            'cities_url': 'https://api.ozonexpress.ma/cities',
            'auth_mode': 'path',
            'parcel_stock': 0,
            'parcel_open': 1,
            'parcel_fragile': 1,
            'parcel_replace': 0,
        },
        'secrets': {
            'client_id': '12345',
            'api_key': 'private-ozon-key',
        },
    })
    assert integration_r.status_code == 200, integration_r.text
    integration = integration_r.json()

    captured = {}

    class FakeResponse:
        status_code = 200
        text = '{"TRACKING-NUMBER":"OZE123456789"}'

        def json(self):
            return {
                'TRACKING-NUMBER': 'OZE123456789',
                'RECEIVER': 'Mohammed Alami',
                'PHONE': '0612345678',
                'CITY_ID': '1',
                'CITY_NAME': 'Casablanca',
                'ADDRESS': '123 Rue Hassan II',
                'PRICE': '398',
                'DELIVERED-PRICE': '25',
                'RETURNED-PRICE': '15',
                'REFUSED-PRICE': '15',
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, headers=None):
            # City sync used by _city_id()
            class CityResponse:
                status_code = 200
                text = '{}'

                def raise_for_status(self):
                    pass

                def json(self):
                    return {
                        'CITIES': {
                            '1': {
                                'ID': '1',
                                'NAME': 'Casablanca',
                                'DELIVERED-PRICE': '25',
                            }
                        }
                    }
            return CityResponse()

        def post(self, url, files=None, headers=None):
            captured['url'] = url
            captured['files'] = files or {}
            captured['headers'] = headers or {}
            return FakeResponse()

    monkeypatch.setattr(httpx, 'Client', FakeClient)

    dispatch_r = client.post(
        f"/api/v1/integrations/ozon-express/{integration['id']}/dispatch/{order['id']}"
    )

    assert dispatch_r.status_code == 200, dispatch_r.text
    body = dispatch_r.json()

    assert body['ok'] is True
    assert body['tracking_number'] == 'OZE123456789'
    assert body['delivery_status'] == 'DISPATCHED'

    assert captured['url'] == (
        'https://api.ozonexpress.ma/customers/12345/private-ozon-key/add-parcel'
    )

    form = {k: v[1] for k, v in captured['files'].items()}

    assert form['parcel-receiver'] == 'Mohammed Alami'
    assert form['parcel-phone'] == '0612345678'
    assert form['parcel-city'] == '1'
    assert form['parcel-address'] == '123 Rue Hassan II'
    assert form['parcel-price'] == '398.00'
    assert form['parcel-stock'] == '0'
    assert form['parcel-open'] == '1'
    assert form['parcel-fragile'] == '1'
    assert form['parcel-replace'] == '0'

    products_payload = _json.loads(form['products'])
    assert products_payload == [{'ref': 'OZON-DISPATCH-1', 'qnty': 2}]

    shipments = client.get(
        f"/api/v1/delivery/shipments?integration_id={integration['id']}"
    ).json()

    assert any(
        s['provider'] == 'OZON_EXPRESS'
        and s['tracking_number'] == 'OZE123456789'
        and s['status'] == 'DISPATCHED'
        for s in shipments
    )

    assert 'private-ozon-key' not in dispatch_r.text


def test_google_sheets_batch_isolation_dry_run_and_idempotency(client):
    store = client.get('/api/v1/stores').json()[0]
    sku = 'SHEETS-ISO-1'
    r = client.post('/api/v1/products', json={
        'store_id': store['id'], 'name': 'Iso Product', 'sku': sku,
        'selling_price': 100, 'currency': 'MAD', 'commission_per_confirmation': 5, 'offers': []
    })
    assert r.status_code == 200, r.text
    integ = client.post('/api/v1/integrations', json={
        'provider': 'GOOGLE_SHEETS', 'name': 'Iso Sheet', 'store_id': store['id'],
        'config': {'sheet_name': 'orders', 'auto_assign': False}, 'secrets': {}
    }).json()
    script = client.get(f"/api/v1/integrations/google-sheets/{integ['id']}/script").json()
    token = parse_qs(urlparse(script['webhook_url']).query)['token'][0]
    assert 'SOURCE_SHEET_NAME = "orders"' in script['script']
    assert 'resendAllRowsToCallCenter' in script['script']
    url = f"/api/v1/integrations/google-sheets/{integ['id']}/webhook?token={token}"
    rows = [
        {'row_number': 2, 'sku': sku, 'customer_name': 'Iso A', 'phone': '0611111111', 'external_order_id': 'iso-1'},
        {'row_number': 3, 'sku': sku, 'customer_name': 'Iso B', 'phone': '0622222222', 'quantity': 0, 'external_order_id': 'iso-2'},  # invalid
        {'row_number': 4, 'sku': 'NOPE', 'customer_name': 'Iso C', 'phone': '0633333333', 'external_order_id': 'iso-3'},  # unknown SKU
        {'row_number': 5, 'sku': sku, 'customer_name': 'Iso D', 'phone': '0644444444', 'external_order_id': 'iso-4'},
    ]
    count = lambda: len(client.get('/api/v1/orders?search=Iso').json())
    before = count()

    dry = client.post(url + '&dry_run=true', json={'orders': rows}).json()
    assert dry['summary']['would_insert'] == 2 and dry['summary']['failed'] == 2
    assert count() == before  # dry run writes nothing

    live = client.post(url, json={'orders': rows}).json()
    assert live['summary'] == {**live['summary'], 'received': 4, 'inserted': 2, 'duplicate': 0, 'failed': 2}
    assert count() == before + 2  # bad rows did not block good rows

    again = client.post(url, json={'orders': rows}).json()
    assert again['summary']['inserted'] == 0 and again['summary']['duplicate'] == 2
    assert count() == before + 2  # idempotent resend
    assert 'token' not in str(live['summary'])


def test_google_sheets_header_token_long_values_and_no_event_flood(client):
    from app.core.db import SessionLocal
    from app.models import IntegrationEvent
    store = client.get('/api/v1/stores').json()[0]
    sku = 'SHEETS-HDR-1'
    assert client.post('/api/v1/products', json={'store_id': store['id'], 'name': 'Hdr', 'sku': sku, 'selling_price': 50, 'currency': 'MAD', 'commission_per_confirmation': 1, 'offers': []}).status_code == 200
    integ = client.post('/api/v1/integrations', json={'provider': 'GOOGLE_SHEETS', 'name': 'Hdr', 'store_id': store['id'], 'config': {'sheet_name': 'orders', 'auto_assign': False}, 'secrets': {}}).json()
    script = client.get(f"/api/v1/integrations/google-sheets/{integ['id']}/script").json()
    token = parse_qs(urlparse(script['webhook_url']).query)['token'][0]
    assert 'X-Webhook-Token' in script['script']
    url = f"/api/v1/integrations/google-sheets/{integ['id']}/webhook"
    assert client.post(url, json={'orders': []}).status_code == 401
    assert client.post(url, json={'orders': []}, headers={'X-Webhook-Token': 'wrong'}).status_code == 401
    body = {'orders': [
        {'row_number': 2, 'sku': sku, 'customer_name': 'Long City', 'phone': '0655555555', 'city': 'X' * 300, 'external_order_id': 'hdr-1'},
        {'row_number': 3, 'sku': '', 'customer_name': 'No Sku', 'phone': '0666666666', 'external_order_id': 'hdr-2'},
    ]}
    for _ in range(3):
        res = client.post(url, json=body, headers={'X-Webhook-Token': token}).json()
    assert res['summary']['duplicate'] == 1 and res['summary']['failed'] == 1
    assert res['summary']['failure_reasons']['Product SKU not found: (empty)']['sample_rows'] == [3]
    with SessionLocal() as db:
        failed_events = db.query(IntegrationEvent).filter(IntegrationEvent.integration_id == integ['id'], IntegrationEvent.status == 'FAILED').count()
    assert failed_events == 3  # one BATCH_SUMMARY per batch, not one per failing row


def _sheet_setup(client, skus=('SHEETS-C1',), sheet_name='orders', extra_config=None):
    store = client.get('/api/v1/stores').json()[0]
    prods = {}
    for sku in skus:
        r = client.post('/api/v1/products', json={'store_id': store['id'], 'name': sku, 'sku': sku, 'selling_price': 100, 'currency': 'MAD', 'commission_per_confirmation': 1, 'offers': []})
        assert r.status_code == 200, r.text
        prods[sku] = r.json()
    integ = client.post('/api/v1/integrations', json={'provider': 'GOOGLE_SHEETS', 'name': 'Reg ' + skus[0], 'store_id': store['id'], 'config': {'sheet_name': sheet_name, 'auto_assign': False, **(extra_config or {})}, 'secrets': {}}).json()
    script = client.get(f"/api/v1/integrations/google-sheets/{integ['id']}/script").json()
    token = parse_qs(urlparse(script['webhook_url']).query)['token'][0]
    url = f"/api/v1/integrations/google-sheets/{integ['id']}/webhook"
    send = lambda orders, **kw: client.post(url + ('?dry_run=true' if kw.get('dry') else ''), json={'orders': orders}, headers={'X-Webhook-Token': token}).json()
    return integ, send


def test_sheet_id_collision_is_imported_not_dropped_and_stays_idempotent(client):
    integ, send = _sheet_setup(client, ('SHEETS-C1', 'SHEETS-C2'))
    a = {'row_number': 2, 'sku': 'SHEETS-C1', 'customer_name': 'First', 'phone': '0671000001', 'external_order_id': 'COLL-7'}
    assert send([a])['results'][0]['outcome'] == 'INSERTED'
    # same id, different customer (re-used id / second feed): previously silently dropped as a "duplicate"
    b = {**a, 'row_number': 9, 'customer_name': 'Second', 'phone': '0671000002'}
    res = send([b])['results'][0]
    assert res['outcome'] == 'INSERTED' and res['collision'] is True
    # same id + same phone, different SKU (multi-line order)
    c = {**a, 'row_number': 3, 'sku': 'SHEETS-C2'}
    assert send([c])['results'][0]['outcome'] == 'INSERTED'
    # everything re-sent -> only true duplicates, nothing new
    again = send([a, b, c])
    assert [r['outcome'] for r in again['results']] == ['DUPLICATE'] * 3
    assert again['summary']['inserted'] == 0
    # row position moved (sheet sorted): still the same lead
    assert send([{**a, 'row_number': 500}])['results'][0]['outcome'] == 'DUPLICATE'


def test_sheet_blank_order_id_uses_stable_fingerprint_not_row_position(client):
    integ, send = _sheet_setup(client, ('SHEETS-F1',))
    lead = {'row_number': 5, 'sku': 'SHEETS-F1', 'customer_name': 'No Id', 'phone': '0672000001', 'quantity': 2, 'total_price': 150, 'lead_date': '2026-11-01'}
    first = send([lead])['results'][0]
    assert first['outcome'] == 'INSERTED'
    # different row (sheet re-sorted / row reused by ANOTHER lead must not collide)
    assert send([{**lead, 'row_number': 77}])['results'][0]['outcome'] == 'DUPLICATE'
    other = {**lead, 'customer_name': 'Different', 'phone': '0672000002'}   # another lead at the old row position
    assert send([{**other, 'row_number': 5}])['results'][0]['outcome'] == 'INSERTED'
    # legacy row-position id from the old script: same phone => duplicate, new phone => insert
    legacy = {**lead, 'external_order_id': 'sheet:SSID:orders:5'}
    assert send([legacy])['results'][0]['outcome'] == 'DUPLICATE'


def test_sheet_outcomes_rejected_vs_failed_and_no_default_for_unknown_sku(client):
    integ, send = _sheet_setup(client, ('SHEETS-R1',))
    res = send([
        {'row_number': 2, 'sku': 'UNKNOWN-SKU', 'customer_name': 'U', 'phone': '0673000001', 'external_order_id': 'rej-1'},
        {'row_number': 3, 'sku': '', 'customer_name': 'E', 'phone': '0673000002', 'external_order_id': 'rej-2'},
        {'row_number': 4, 'sku': 'SHEETS-R1', 'customer_name': 'P', 'phone': '12', 'external_order_id': 'rej-3'},
        {'row_number': 5, 'sku': 'SHEETS-R1', 'customer_name': 'Ok', 'phone': '0673000003', 'external_order_id': 'rej-4'},
    ])
    assert [r['outcome'] for r in res['results']] == ['REJECTED', 'REJECTED', 'REJECTED', 'INSERTED']
    assert res['summary']['rejected'] == 3 and res['summary']['inserted'] == 1 and res['summary']['failed'] == 3
    # a default product must never absorb a NON-empty unknown SKU
    prod = client.get('/api/v1/products?status=ACTIVE').json()[0]
    integ2, send2 = _sheet_setup(client, ('SHEETS-R2',), extra_config={'default_product_id': prod['id']})
    r2 = send2([{'row_number': 2, 'sku': 'UNKNOWN-SKU', 'customer_name': 'U', 'phone': '0673000009', 'external_order_id': 'rej-9'}])['results'][0]
    assert r2['outcome'] == 'REJECTED'


def test_sheet_sync_status_endpoint(client):
    integ, send = _sheet_setup(client, ('SHEETS-S1',))
    send([{'row_number': 2, 'sku': 'SHEETS-S1', 'customer_name': 'S', 'phone': '0674000001', 'external_order_id': 'st-1'},
          {'row_number': 3, 'sku': 'NOPE', 'customer_name': 'S', 'phone': '0674000002', 'external_order_id': 'st-2'}])
    st = client.get(f"/api/v1/integrations/google-sheets/{integ['id']}/sync-status").json()
    assert st['last_successful_import_at'] and sum(st['imported_per_day'].values()) >= 1
    assert st['last_batch']['inserted'] == 1 and st['last_batch']['rejected'] == 1
    assert 'Product SKU not found: NOPE' in st['last_batch']['failure_reasons']
    assert st['sheet_name_warning'] is None
    assert 'token' not in str(st).lower()


def test_generated_apps_script_executes_correctly_in_node(client, tmp_path):
    import shutil, subprocess
    from pathlib import Path
    import pytest
    if not shutil.which('node'):
        pytest.skip('node not available')
    integ, _ = _sheet_setup(client, ('SHEETS-N1',))
    script = client.get(f"/api/v1/integrations/google-sheets/{integ['id']}/script").json()['script']
    f = tmp_path / 'generated.js'
    f.write_text(script)
    out = subprocess.run(['node', str(Path(__file__).parent / 'appsscript_harness.js'), str(f)], capture_output=True, text=True)
    assert out.returncode == 0 and 'APPS_SCRIPT_HARNESS_OK' in out.stdout, out.stdout + out.stderr


def test_webhook_records_feed_identity_and_sync_status_lists_feeds(client):
    integ, send_ = _sheet_setup(client, ('SHEETS-FD1',))
    store = client.get('/api/v1/stores').json()[0]
    script = client.get(f"/api/v1/integrations/google-sheets/{integ['id']}/script").json()
    token = parse_qs(urlparse(script['webhook_url']).query)['token'][0]
    url = f"/api/v1/integrations/google-sheets/{integ['id']}/webhook"
    row = {'row_number': 2, 'sku': 'SHEETS-FD1', 'customer_name': 'F', 'phone': '0675000001', 'external_order_id': 'fd-1'}
    client.post(url, json={'client': {'spreadsheet': 'abc123', 'tab': 'orders', 'version': 'v2'}, 'orders': [row]}, headers={'X-Webhook-Token': token})
    client.post(url, json={'client': {'spreadsheet': 'old999', 'tab': 'Sheet1', 'version': 'v2'}, 'orders': [{**row, 'sku': 'NOPE', 'external_order_id': 'fd-2', 'phone': '0675000002'}]}, headers={'X-Webhook-Token': token})
    st = client.get(f"/api/v1/integrations/google-sheets/{integ['id']}/sync-status").json()
    assert st['feeds_last_7_days']['abc123/orders']['inserted'] == 1
    assert st['feeds_last_7_days']['old999/Sheet1']['rejected'] == 1


# ----------------------------- regression suite for the lead-loss incident -----------------------------
def _orders_with_ext(client, ext_prefix):
    return [o for o in client.get('/api/v1/orders?search=').json() if str(o.get('external_order_id') or '').startswith(ext_prefix)]


def test_same_customer_legitimate_repeat_orders_are_preserved(client):
    integ, send = _sheet_setup(client, ('SHEETS-RP1',))
    base = {'sku': 'SHEETS-RP1', 'customer_name': 'Repeat', 'phone': '0678000001', 'quantity': 1}
    a = send([{**base, 'row_number': 2, 'external_order_id': 'rp-1', 'total_price': 100}])['results'][0]
    b = send([{**base, 'row_number': 3, 'external_order_id': 'rp-2', 'total_price': 100}])['results'][0]       # new order id, same customer
    c = send([{**base, 'row_number': 4, 'total_price': 100, 'lead_date': '2026-11-01'}])['results'][0]        # no id, same customer/product
    d = send([{**base, 'row_number': 5, 'total_price': 100, 'lead_date': '2026-11-02'}])['results'][0]        # no id, later day
    assert [x['outcome'] for x in (a, b, c, d)] == ['INSERTED'] * 4
    assert len({x['order_number'] for x in (a, b, c, d)}) == 4


def test_shared_id_sequences_across_spreadsheets_and_stores(client):
    # two different spreadsheets (feeds) reuse the same numeric ids for different customers
    integ, send = _sheet_setup(client, ('SHEETS-MS1',))
    sc = lambda ss, p: send([{'row_number': 2, 'sku': 'SHEETS-MS1', 'customer_name': ss, 'phone': p, 'external_order_id': '5001'}])
    r1 = sc('Feed A', '0679000001')['results'][0]; r2 = sc('Feed B', '0679000002')['results'][0]; r3 = sc('Feed C', '0679000003')['results'][0]
    assert [r['outcome'] for r in (r1, r2, r3)] == ['INSERTED'] * 3 and [bool(r['collision']) for r in (r1, r2, r3)] == [False, True, True]
    assert [sc('Feed B', '0679000002')['results'][0]['outcome'], sc('Feed C', '0679000003')['results'][0]['outcome']] == ['DUPLICATE'] * 2
    # two stores sharing the same id sequence never interfere (dedupe is per store)
    s2 = client.post('/api/v1/stores', json={'name': 'Second Store', 'code': 'S2X'})
    assert s2.status_code == 200, s2.text
    store2 = s2.json()
    assert client.post('/api/v1/products', json={'store_id': store2['id'], 'name': 'P', 'sku': 'SHEETS-MS1-S2', 'selling_price': 100, 'currency': 'MAD', 'commission_per_confirmation': 1, 'offers': []}).status_code == 200
    integ2 = client.post('/api/v1/integrations', json={'provider': 'GOOGLE_SHEETS', 'name': 'Store2 sheet', 'store_id': store2['id'], 'config': {'sheet_name': 'orders', 'auto_assign': False}, 'secrets': {}}).json()
    scr = client.get(f"/api/v1/integrations/google-sheets/{integ2['id']}/script").json()
    tok2 = parse_qs(urlparse(scr['webhook_url']).query)['token'][0]
    res = client.post(f"/api/v1/integrations/google-sheets/{integ2['id']}/webhook", json={'orders': [{'row_number': 2, 'sku': 'SHEETS-MS1-S2', 'customer_name': 'Feed A', 'phone': '0679000001', 'external_order_id': '5001'}]}, headers={'X-Webhook-Token': tok2}).json()
    assert res['results'][0]['outcome'] == 'INSERTED' and not res['results'][0]['collision']


def test_quantity_total_and_validation_rules(client):
    integ, send = _sheet_setup(client, ('SHEETS-Q1',))
    res = send([
        {'row_number': 2, 'sku': 'SHEETS-Q1', 'customer_name': 'Qty', 'phone': '0680000001', 'quantity': 3, 'total_price': 450, 'external_order_id': 'q-1'},
        {'row_number': 3, 'sku': 'SHEETS-Q1', 'customer_name': '', 'phone': '0680000002', 'external_order_id': 'q-2'},      # blank name still has a phone: imported with default? -> must be explicit
        {'row_number': 4, 'sku': 'SHEETS-Q1', 'phone': '0680000003', 'external_order_id': 'q-3'},                          # missing name key -> validation reject
        {'row_number': 5, 'sku': 'SHEETS-Q1', 'customer_name': 'Bad Phone', 'phone': '123', 'external_order_id': 'q-4'},
        {'row_number': 6, 'sku': 'SHEETS-Q1', 'customer_name': 'Neg', 'phone': '0680000005', 'total_price': -5, 'external_order_id': 'q-5'},
    ])
    out = {r['row_number']: r for r in res['results']}
    assert out[2]['outcome'] == 'INSERTED'
    assert out[4]['outcome'] == 'REJECTED' and 'customer_name' in out[4]['error']
    assert out[5]['outcome'] == 'REJECTED' and 'phone' in out[5]['error'].lower()
    assert out[6]['outcome'] == 'REJECTED'
    order = next(o for o in client.get('/api/v1/orders?search=Qty').json() if o['external_order_id'] == 'q-1')
    assert order['quantity'] == 3 and float(order['total_price']) == 450.0 and abs(float(order['unit_price']) - 150.0) < 1e-6


def test_unique_index_blocks_double_insert_and_race_is_reported_as_duplicate(client, monkeypatch):
    from decimal import Decimal
    import pytest
    from sqlalchemy.exc import IntegrityError
    from app.core.db import SessionLocal
    from app.models import Customer, Order, Product
    from app.services import google_sheets as gs

    integ, send = _sheet_setup(client, ('SHEETS-RC1',))
    store_id = client.get('/api/v1/stores').json()[0]['id']
    first = send([{'row_number': 2, 'sku': 'SHEETS-RC1', 'customer_name': 'Race', 'phone': '0681000001', 'external_order_id': 'race-1'}])['results'][0]
    assert first['outcome'] == 'INSERTED'
    # 1) the database itself refuses a second order with the same (store, source id)
    with SessionLocal() as db:
        src = db.query(Order).filter(Order.external_order_id == 'race-1').one()
        db.add(Order(order_number='CC-DUP-TEST', store_id=src.store_id, product_id=src.product_id, customer_id=src.customer_id, quantity=1, unit_price=1, total_price=1, currency='MAD', source='GOOGLE_SHEETS', external_order_id='race-1', call_status='NEW'))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    # 2) race: a concurrent request inserts the same lead after our lookup but before our insert
    def racing_choose_agent(db, product_id, customer_id):
        prod = db.query(Product).filter(Product.id == product_id).one()
        db.add(Order(order_number='CC-RACE-WINNER', store_id=prod.store_id, product_id=product_id, customer_id=customer_id, quantity=1, unit_price=Decimal('100'), total_price=Decimal('100'), currency='MAD', source='GOOGLE_SHEETS', external_order_id='race-2', call_status='NEW'))
        db.flush()
        return None
    monkeypatch.setattr(gs, 'choose_agent', racing_choose_agent)
    integ2, send2 = _sheet_setup(client, ('SHEETS-RC2',), extra_config={'auto_assign': True})
    res = send2([{'row_number': 2, 'sku': 'SHEETS-RC2', 'customer_name': 'Race2', 'phone': '0681000002', 'external_order_id': 'race-2'}])
    # the winner belongs to the same customer but another product(SKU) is irrelevant: same store+id+phone => duplicate, never two orders
    assert res['results'][0]['outcome'] == 'DUPLICATE'
    assert len([o for o in client.get('/api/v1/orders?search=').json() if o['external_order_id'] == 'race-2']) == 1


def test_api_counts_match_database_and_dashboard(client):
    integ, send = _sheet_setup(client, ('SHEETS-DB1',))
    before = client.get('/api/v1/analytics/overview?range=today').json()['leads']
    n = 4
    send([{'row_number': i + 2, 'sku': 'SHEETS-DB1', 'customer_name': f'Dash{i}', 'phone': f'068200000{i}', 'external_order_id': f'dash-{i}'} for i in range(n)])
    send([{'row_number': i + 2, 'sku': 'SHEETS-DB1', 'customer_name': f'Dash{i}', 'phone': f'068200000{i}', 'external_order_id': f'dash-{i}'} for i in range(n)])  # repeat webhook
    after = client.get('/api/v1/analytics/overview?range=today').json()['leads']
    assert after - before == n
    page = client.get('/api/v1/orders/paginated?limit=100&offset=0&search=Dash').json()
    assert (page['total'] if isinstance(page, dict) and 'total' in page else len(page)) >= n


def test_source_identity_is_persisted_and_feed_silence_alert(client):
    from datetime import timedelta
    from app.core.db import SessionLocal
    from app.models import IntegrationEvent
    from app.core.time import utcnow
    integ, send_ = _sheet_setup(client, ('SHEETS-SI1',))
    script = client.get(f"/api/v1/integrations/google-sheets/{integ['id']}/script").json()
    token = parse_qs(urlparse(script['webhook_url']).query)['token'][0]
    url = f"/api/v1/integrations/google-sheets/{integ['id']}/webhook"
    r = client.post(url, json={'client': {'spreadsheet': 'abc123', 'tab': 'orders', 'version': 'v2'}, 'orders': [{'row_number': 7, 'sku': 'SHEETS-SI1', 'customer_name': 'Src', 'phone': '0676000001', 'external_order_id': 'si-1'}]}, headers={'X-Webhook-Token': token}).json()
    assert r['results'][0]['outcome'] == 'INSERTED'
    with SessionLocal() as db:
        ev = db.query(IntegrationEvent).filter(IntegrationEvent.integration_id == integ['id'], IntegrationEvent.event_type == 'ORDER_IMPORT', IntegrationEvent.status == 'SUCCESS').one()
        assert ev.payload['source'] == {'spreadsheet': 'abc123', 'tab': 'orders', 'version': 'v2'} and ev.payload['row_number'] == 7
        # simulate a feed that delivered plenty of leads but has been silent for >24h
        for i in range(10):
            db.add(IntegrationEvent(integration_id=integ['id'], provider='GOOGLE_SHEETS', direction='INBOUND', event_type='BATCH_SUMMARY', status='SUCCESS',
                                    payload={'received': 1, 'inserted': 1, 'rejected': 0, 'client': {'spreadsheet': 'quiet99', 'tab': 'orders', 'version': 'v2'}}, created_at=utcnow() - timedelta(hours=30 + i)))
        db.commit()
    st = client.get(f"/api/v1/integrations/google-sheets/{integ['id']}/sync-status").json()
    assert any('quiet99/orders' in a and 'none in the last 24h' in a for a in st['alerts']), st['alerts']
