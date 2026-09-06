def test_product_agent_order_and_individual_payout(client):
    store = client.get('/api/v1/stores').json()[0]
    product_r = client.post('/api/v1/products', json={
        'store_id': store['id'],
        'name': 'Test Product',
        'sku': 'TEST-SKU-1',
        'selling_price': 299,
        'currency': 'MAD',
        'commission_per_confirmation': 5,
        'offers': []
    })
    assert product_r.status_code == 200
    product = product_r.json()

    agents = []
    for username, display_name in [('agent_one', 'Agent One'), ('agent_two', 'Agent Two')]:
        r = client.post('/api/v1/agents', json={
            'username': username,
            'password': 'StrongPass123!',
            'display_name': display_name,
            'commission_default': 5,
            'product_ids': [product['id']]
        })
        assert r.status_code == 200
        agents.append(r.json())

    for agent, phone in zip(agents, ['0610101010', '0620202020']):
        order_r = client.post('/api/v1/orders/manual', json={
            'store_id': store['id'],
            'product_id': product['id'],
            'customer_name': 'Customer',
            'phone': phone,
            'city': 'Casablanca',
            'assigned_agent_id': agent['id'],
            'call_status': 'NEW'
        })
        assert order_r.status_code == 200
        order = order_r.json()
        confirmed = client.patch(f"/api/v1/orders/{order['id']}", json={'call_status': 'CONFIRMED'})
        assert confirmed.status_code == 200

    balances = {x['display_name']: x for x in client.get('/api/v1/payments/agents').json()}
    assert balances['Agent One']['unpaid_balance'] == '5.00'
    assert balances['Agent Two']['unpaid_balance'] == '5.00'

    pay = client.post(f"/api/v1/payments/agents/{agents[0]['id']}/pay", json={'payment_method': 'CASH'})
    assert pay.status_code == 200
    assert pay.json()['remaining_unpaid_balance'] == '0'

    balances = {x['display_name']: x for x in client.get('/api/v1/payments/agents').json()}
    assert balances['Agent One']['unpaid_balance'] == '0'
    assert balances['Agent Two']['unpaid_balance'] == '5.00'


def test_dashboard_date_ranges(client):
    for name in ['today', 'yesterday', 'last7', 'last30', 'this_month', 'last_month']:
        r = client.get(f'/api/v1/analytics/overview?range={name}')
        assert r.status_code == 200
        assert 'leads' in r.json()
