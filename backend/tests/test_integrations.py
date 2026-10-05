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
