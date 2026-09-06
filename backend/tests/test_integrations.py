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
