import hashlib
import hmac
import time
from urllib.parse import urlencode
import httpx
import pytest
from app.core.db import SessionLocal
from app.models import Order, DeliveryShipment
from app.services import ameex


def test_real_city_envelope():
    payload = {"type": "success", "msg": "", "cities": {
        "1": {"id": 1, "name": "Marrakech"},
        "2": {"id": 2, "name": "Meknes"},
    }, "sandbox": 1}
    assert ameex._collection(payload, "CITIES") == list(payload["cities"].values())


def test_city_response_diagnostic(monkeypatch):
    secrets = {"client_id": "demo-id", "api_key": "test_demo", "webhook_secret": "secret"}
    monkeypatch.setattr(ameex, "_settings", lambda integration: ({}, secrets))
    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, url, headers, data):
            return httpx.Response(200, json={"type": "warning", "msg": "Blocked test_demo", "data": None},
                                  request=httpx.Request(method, url))
    monkeypatch.setattr(ameex.httpx, "Client", FakeClient)
    result = ameex.test_connection(None)
    assert result["ok"] is False
    assert "cities=missing" in result["message"] and "data=NoneType" in result["message"]
    assert "msg=Blocked [redacted]" in result["message"]


def test_api_error_and_trimmed_credentials(monkeypatch):
    secrets = {"client_id": " demo-id ", "api_key": " test_demo ", "webhook_secret": "signing-secret"}
    monkeypatch.setattr(ameex, "_settings", lambda integration: ({}, secrets))
    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, url, headers, data):
            assert headers["C-Api-Id"] == "demo-id"
            assert headers["C-Api-Key"] == "test_demo"
            return httpx.Response(200, json={"type": "error", "msg": "Invalid key test_demo demo-id signing-secret"},
                                  request=httpx.Request(method, url))
    monkeypatch.setattr(ameex.httpx, "Client", FakeClient)
    with pytest.raises(ameex.AmeexError) as error:
        ameex._request(None, "GET", "/Delivery/Cities")
    message = str(error.value)
    assert message.startswith("AMEEX: Invalid key") and message.count("[redacted]") == 3
    assert all(secret.strip() not in message for secret in secrets.values())


def setup(client):
    store = client.get('/api/v1/stores').json()[0]
    result = client.post('/api/v1/integrations', json={'provider':'AMEEX','name':'Test','store_id':store['id'],
        'secrets':{'client_id':'demo-id','api_key':'test_demo','webhook_secret':'signing-secret'}})
    assert result.status_code == 200, result.text
    assert 'test_demo' not in result.text and 'signing-secret' not in result.text
    return store, result.json()


def mock(monkeypatch, calls, fail=False):
    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs['follow_redirects'] is False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, url, headers, data):
            calls.append((method,url,headers,data))
            if fail and method == 'POST': raise httpx.ReadTimeout('Timeout')
            body = {'CITIES':[{'ID':'1','NAME':'Casablanca'}]} if url.endswith('/Cities') else {'PARCEL_CODE':'AMX-'+str(len(calls))}
            return httpx.Response(200,json=body,request=httpx.Request(method,url))
    monkeypatch.setattr(ameex.httpx,'Client',FakeClient)


def order(client, store):
    p=client.post('/api/v1/products',json={'store_id':store['id'],'name':'AMEEX Product','sku':f'AMX-{time.time_ns()}',
        'selling_price':199,'currency':'MAD','commission_per_confirmation':5,'offers':[]}).json()
    r=client.post('/api/v1/orders/manual',json={'store_id':store['id'],'product_id':p['id'],'customer_name':'Test Receiver',
        'phone':'0677777777','city':'Casablanca','address':'Test address','quantity':2,'call_status':'CONFIRMED'})
    assert r.status_code == 200,r.text
    return r.json()


def signed(client, integration, raw, secret='signing-secret', ts=None):
    ts=str(ts or int(time.time()))
    sig=hmac.new(secret.encode(),ts.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    return client.post(f"/api/v1/integrations/ameex/{integration['id']}/webhook",content=raw,
        headers={'Content-Type':'application/x-www-form-urlencoded','X-Ameex-Signature':f't={ts},v1={sig}'})


def test_dispatch_and_webhook(client, monkeypatch):
    store,i=setup(client); o=order(client,store); calls=[]; mock(monkeypatch,calls)
    path=f"/api/v1/integrations/ameex/{i['id']}/dispatch/{o['id']}"
    r=client.post(path)
    assert r.status_code == 200,r.text
    tracking=r.json()['tracking_number']
    method,url,headers,p=calls[-1]
    assert method=='POST' and url==ameex.BASE_URL+'/Delivery/Parcels/Action/Type/Add'
    assert headers['C-Api-Id']=='demo-id' and headers['C-Api-Key']=='test_demo'
    assert p=={'type':'SIMPLE','receiver':'Test Receiver','phone':'0677777777','city':'1','cod':'398.00',
        'address':'Test address','product':'AMEEX Product x2','comment':'','order_num':o['order_number']}
    assert client.post(path).status_code==502
    assert len(calls)==2
    raw=urlencode({'CODE':tracking,'STATUT':'DELIVERED','STATUT_NAME':'Livré','COMMENT':'Reçu + merci','SANDBOX':'1'}).encode()
    assert signed(client,i,raw,secret='wrong').status_code==401
    assert signed(client,i,raw,ts=int(time.time())-600).status_code==401
    assert signed(client,i,raw.replace(b'&SANDBOX=1',b'')).status_code==400
    _,other=setup(client)
    assert signed(client,other,raw).json()['matched'] is False
    r=signed(client,i,raw)
    assert r.status_code==200 and r.json()['delivery_status']=='DELIVERED',r.text
    assert signed(client,i,raw).json()['duplicate'] is True
    with SessionLocal() as db: assert db.get(Order,o['id']).delivery_status=='DELIVERED'
    assert 'token=' not in client.get(f"/api/v1/integrations/{i['id']}/webhook-config").json()['webhook_url']


def test_unknown_dispatch_blocks_retry(client, monkeypatch):
    store,i=setup(client); o=order(client,store); calls=[]; mock(monkeypatch,calls,True)
    path=f"/api/v1/integrations/ameex/{i['id']}/dispatch/{o['id']}"
    assert client.post(path).status_code==502
    assert client.post(path).status_code==502
    assert len(calls)==2
    with SessionLocal() as db:
        assert db.query(DeliveryShipment).filter_by(order_id=o['id'],provider='AMEEX').one().status=='UNKNOWN'


def test_configuration_tracking_and_limits(client,monkeypatch):
    store,i=setup(client); calls=[]; mock(monkeypatch,calls)
    assert client.post('/api/v1/integrations',json={'provider':'AMEEX','name':'Invalid','store_id':store['id']}).status_code==400
    assert client.patch(f"/api/v1/integrations/{i['id']}",json={'store_id':None}).status_code==400
    assert client.post(f"/api/v1/integrations/{i['id']}/test").json()['cities_synced']==1
    prefix=f"/api/v1/integrations/ameex/{i['id']}"
    for endpoint in ('mass-tracking','mass-info'):
        for codes in ([],['x']*101,['x,y']): assert client.post(prefix+'/'+endpoint,json=codes).status_code==400
        assert client.post(prefix+'/'+endpoint,json=['x','y']).status_code==200
        assert calls[-1][3]=={'codes':'x,y'}
    assert client.get(prefix+'/tracking/AMX123').status_code==200
    assert calls[-1][1].endswith('/Tracking/ParcelCode/AMX123')
    assert client.get(prefix+'/statuses').status_code==200
    assert calls[-1][1].endswith('/Statuts')


def test_raw_body_signature_and_unknown_status(client, monkeypatch):
    store,i=setup(client); o=order(client,store); calls=[]; mock(monkeypatch,calls)
    result=client.post(f"/api/v1/integrations/ameex/{i['id']}/dispatch/{o['id']}").json()
    tracking=result['tracking_number']
    raw=urlencode({'CODE':tracking,'STATUT':'UNRECOGNIZED','COMMENT':'space here','SANDBOX':'1'}).encode()
    ts=str(int(time.time()))
    sig=hmac.new(b'signing-secret',ts.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    response=client.post(f"/api/v1/integrations/ameex/{i['id']}/webhook",content=raw.replace(b'+',b'%20'),
        headers={'Content-Type':'application/x-www-form-urlencoded','X-Ameex-Signature':f't={ts},v1={sig}'})
    assert response.status_code==401
    assert signed(client,i,raw).status_code==200
    with SessionLocal() as db: assert db.get(Order,o['id']).delivery_status=='DISPATCHED'
    unsigned=client.post(f"/api/v1/integrations/ameex/{i['id']}/webhook",content=raw)
    assert unsigned.status_code==401
    client.patch(f"/api/v1/integrations/{i['id']}",json={'is_active':False})
    assert signed(client,i,raw).status_code==409


def test_missing_parcel_code_blocks_retry(client,monkeypatch):
    store,i=setup(client); o=order(client,store); calls=[]
    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def request(self,method,url,headers,data):
            calls.append(method)
            body={'CITIES':[{'ID':'1','NAME':'Casablanca'}]} if method=='GET' else {'success':True}
            return httpx.Response(200,json=body,request=httpx.Request(method,url))
    monkeypatch.setattr(ameex.httpx,'Client',FakeClient)
    path=f"/api/v1/integrations/ameex/{i['id']}/dispatch/{o['id']}"
    assert client.post(path).status_code==502
    assert client.post(path).status_code==502
    assert calls==['GET','POST']
