"""STORE_CSV_BACKFILL: classification, idempotent import, historical (non-acquisition) accounting, assignment. Synthetic data only."""
import sys
from decimal import Decimal

import pytest

from app.core.db import SessionLocal
from app.core.sources import BACKFILL_SOURCE
from app.models import AgentProduct, Customer, DeliveryShipment, IntegrationEvent, Order, OrderAssignment, PayoutEntry, Product, User
from app.services import csv_backfill as cb
from app.services.csv_backfill import CsvSpec, classify, parse_csv_text
from scripts.assign_batch import run as assign_run
from scripts.csv_backfill import run as backfill_run

HEADER = "SKU,FULL NAME,PHONE NUMBER,city,quantity,total,product name,SHOPIFY ORDER ID\n"


def csv_text(*rows):
    return HEADER + "\n".join(",".join(str(c) for c in r) for r in rows) + "\n"


def spec(name="a.csv", key="alpha", m=None):
    return CsvSpec(name, key, m or {"CSV-SKU": "CBF-1"})


OFFERS = {"CBF-1": {(1, Decimal("199")), (2, Decimal("299"))}}


def existing(**kw):
    base = dict(order_number="CC-X", ext="1", phone="+212600000001", sku="CBF-1", qty=1, total="199.00", source="GOOGLE_SHEETS", day="2026-11-01")
    return {**base, **kw}


def test_classification_rules_without_a_database():
    rows = parse_csv_text(csv_text(
        ("CSV-SKU", "New Person", "212611100001", "Fes", 2, 299, "p", 101),            # NEW
        ("CSV-SKU", "Already Here", "212622200002", "Fes", 1, 199, "p", 102),          # EXISTING (exact phone+sku+qty+total)
        ("CSV-SKU", "Edited Qty", "212633300003", "Fes", 2, 299, "p", 103),            # NEEDS_REVIEW (same phone+sku, other qty/total)
        ("CSV-SKU", "Other Product", "212644400004", "Fes", 1, 199, "p", 104),         # NEW + REPEAT_CUSTOMER (phone has another SKU)
        ("CSV-SKU", "New Person", "212611100001", "Fes", 2, 299, "p", 105),            # DUPLICATE inside the files
        ("CSV-SKU", "", "212655500006", "Fes", 1, 199, "p", 106),                      # INVALID name
        ("CSV-SKU", "Bad Phone", "21261", "Fes", 1, 199, "p", 107),                    # INVALID phone
        ("UNMAPPED", "No Sku Map", "212666600008", "Fes", 1, 199, "p", 108),           # INVALID sku mapping
        ("CSV-SKU", "Same Id Other Data", "212677700009", "Fes", 2, 299, "p", 109),    # CONFLICT
        ("CSV-SKU", "Test Person", "212688800010", "Fes", 1, 199, "p", 110),           # NEEDS_REVIEW (test name)
        ("CSV-SKU", "Odd Total", "212699900011", "Fes", 1, 299.01, "p", 111),          # NEEDS_REVIEW (not a whole price, never rounded)
        ("CSV-SKU", "Weird Price", "212701100012", "Fes", 2, 349, "p", 112),           # NEW + PRICE_NOT_IN_OFFERS
    ), spec(m={"CSV-SKU": "CBF-1"}))
    ex = [existing(phone="+212622200002"), existing(phone="+212633300003", qty=1, total="199.00", order_number="CC-E3"),
          existing(phone="+212644400004", sku="OTHER-SKU", order_number="CC-E4"),
          existing(phone="+212677700009", ext="109", sku="CBF-1", qty=1, total="199.00", order_number="CC-E9")]
    classify(rows, ex, OFFERS)
    got = {r.shopify_id: r.klass for r in rows}
    assert got == {"101": "NEW", "102": "EXISTING", "103": "NEEDS_REVIEW", "104": "NEW", "105": "DUPLICATE", "106": "INVALID", "107": "INVALID", "108": "INVALID",
                   "109": "CONFLICT", "110": "NEEDS_REVIEW", "111": "NEEDS_REVIEW", "112": "NEW"}, got
    by = {r.shopify_id: r for r in rows}
    assert any("REPEAT_CUSTOMER" in f for f in by["104"].flags) and any("PRICE_NOT_IN_OFFERS" in f for f in by["112"].flags)
    assert by["111"].total == Decimal("299.01") and any("not a whole price" in x for x in by["111"].reasons)
    assert by["101"].ext_id == "csv:alpha:101" and not by["101"].flags


def _world(client, sku="CBF-1", sku2="CBF-2"):
    store = client.get('/api/v1/stores').json()[0]
    pid = {}
    for s in (sku, sku2):
        r = client.post('/api/v1/products', json={'store_id': store['id'], 'name': s, 'sku': s, 'selling_price': 199, 'currency': 'MAD', 'commission_per_confirmation': 5,
                                                  'offers': [{'name': '1', 'quantity': 1, 'price': 199}, {'name': '2', 'quantity': 2, 'price': 299}]})
        if r.status_code == 409:                       # already created by an earlier test
            pid[s] = next(p['id'] for p in client.get('/api/v1/products').json() if p['sku'] == s)
            continue
        assert r.status_code == 200, r.text
        pid[s] = r.json()['id']
    return store, pid


def _agents(pids):
    with SessionLocal() as db:
        out = []
        for n in ("Agent A", "Agent B"):
            u = User(username=f"bf_{n[-1].lower()}_{len(pids)}{id(pids)%1000}", password_hash="x", display_name=n, role="AGENT", is_active=True)
            db.add(u); db.flush()
            for p in pids.values():
                db.add(AgentProduct(agent_id=u.id, product_id=p))
            out.append(u.id)
        db.commit()
        return out


def test_end_to_end_dry_run_apply_rerun_include_stores_and_existing_data_untouched(client):
    _world(client, "CBF-1", "CBF-2")
    pre = {}
    with SessionLocal() as db:
        db.add(Customer(name="Pre Existing", phone_raw="0611", phone_e164="+212644400001", city="Rabat", address="Old address"))
        db.commit()
        pre["customers"] = db.query(Customer).count(); pre["orders"] = db.query(Order).count()
    specs = [spec("a.csv", "alpha", {"CSV-SKU": "CBF-1"}), spec("b.csv", "beta", {"CSV-SKU": "CBF-2"})]
    texts = {"a.csv": csv_text(("CSV-SKU", "Alpha One", "212611200010", "Fes", 2, 299, "p", 7), ("CSV-SKU", "Pre Existing", "212644400001", "Salé", 1, 199, "p", 8), ("CSV-SKU", "Test Alpha", "212655500012", "X", 1, 199, "p", 9)),
             "b.csv": csv_text(("CSV-SKU", "Beta One", "212633300011", "Agadir", 1, 199, "p", 7))}   # SAME shopify id 7 in another store
    db = SessionLocal()
    dry = backfill_run(db, texts, "T1", apply=False, include=set(), specs=specs)
    assert dry["classes"] == {"NEW": 3, "NEEDS_REVIEW": 1} and dry["import"]["inserted"] == 3 and dry["orders_before"] == dry["orders_after"]
    with SessionLocal() as chk: assert chk.query(Order).filter(Order.source == BACKFILL_SOURCE).count() == 0      # dry run kept nothing
    res = backfill_run(db, texts, "T1", apply=True, include=set(), specs=specs)
    assert res["import"]["outcomes"] == {"INSERTED": 3} and res["import"]["new_customers"] == 2 and res["orders_after"] == pre["orders"] + 3
    assert res["dashboard_before"]["overview"]["leads"] == res["dashboard_after_inside_transaction"]["overview"]["leads"]    # acquisition untouched
    assert res["dashboard_after_inside_transaction"]["overview"]["backfilled_leads"] == res["dashboard_before"]["overview"]["backfilled_leads"] + 3
    with SessionLocal() as s:
        rows = s.query(Order).filter(Order.source == BACKFILL_SOURCE).all()
        assert {o.external_order_id for o in rows} == {"csv:alpha:7", "csv:alpha:8", "csv:beta:7"}                # store key keeps the equal ids apart
        for o in rows:
            assert o.call_status == "NEW" and o.assigned_agent_id is None and "submission date unknown" in o.call_note
            ev = s.query(IntegrationEvent).filter(IntegrationEvent.entity_id == o.id, IntegrationEvent.status == "SUCCESS").one()
            assert ev.provider == BACKFILL_SOURCE and ev.payload["submitted_at"] == "unknown" and ev.payload["file"] in ("a.csv", "b.csv") and ev.payload["csv_line"] >= 2 and ev.payload["store_key"] in ("alpha", "beta")
            assert s.query(DeliveryShipment).filter(DeliveryShipment.order_id == o.id).count() == 0 and s.query(PayoutEntry).filter(PayoutEntry.order_id == o.id).count() == 0
        c = s.query(Customer).filter(Customer.phone_e164 == "+212644400001").one()
        assert (c.name, c.city, c.address) == ("Pre Existing", "Rabat", "Old address")                              # existing customer untouched
        assert s.query(Customer).count() == pre["customers"] + 2
        # the order of an existing customer is still imported (customer already existing is not a reason to reject)
        assert any(o.external_order_id == "csv:alpha:8" for o in rows)
    # re-importing the same files creates nothing
    again = backfill_run(db, texts, "T1", apply=True, include=set(), specs=specs)
    assert again["classes"].get("EXISTING") == 3 and again["import"]["inserted"] == 0 and again["orders_after"] == res["orders_after"]
    # an explicitly approved review row is imported, but not before
    inc = backfill_run(db, texts, "T1b", apply=True, include={("alpha", 4)}, specs=specs)
    assert inc["import"]["inserted"] == 1
    db.close()


def test_lock_contention_and_cli_guards(client, monkeypatch):
    _world(client, "CBF-1", "CBF-2")
    sp = [spec("c.csv", "gamma", {"CSV-SKU": "CBF-1"})]
    texts = {"c.csv": csv_text(("CSV-SKU", "Gamma One", "212611300001", "Fes", 1, 199, "p", 1))}
    monkeypatch.setattr(cb, "_try_lock", lambda db, key: False)
    db = SessionLocal()
    r = backfill_run(db, texts, "T2", apply=True, include=set(), specs=sp)
    assert r["import"]["outcomes"] == {"FAILED": 1} and r["orders_after"] == r["orders_before"]
    monkeypatch.undo()
    from scripts import csv_backfill as cli
    monkeypatch.setattr(sys, "argv", ["x", "--batch", "B", "--apply"])
    with pytest.raises(SystemExit): cli.main()                                   # --apply without --confirm-batch
    db.close()


def test_assignment_tool_same_customer_one_agent_retry_safe_and_acquisition_untouched(client):
    _, pids = _world(client, "CBF-1", "CBF-2")
    _agents(pids)
    sp = [spec("d.csv", "delta", {"CSV-SKU": "CBF-1"})]
    rows = [("CSV-SKU", f"Delta {i}", "2127" + str(i) * 8, "Fes", 1, 199, "p", 100 + i) for i in range(1, 7)]
    rows.append(("CSV-SKU", "Delta Repeat", "212711111111", "Fes", 2, 299, "p", 200))        # second order, same customer as Delta 1
    texts = {"d.csv": csv_text(*rows)}
    db = SessionLocal()
    kp = lambda: client.get('/api/v1/analytics/overview?range=today').json()
    k0 = kp()
    backfill_run(db, texts, "T3", apply=True, include=set(), specs=sp)
    dry = assign_run(db, BACKFILL_SOURCE, "T3", apply=False)
    assert dry["assigned_now"] == 7 and dry["still_unassigned"] == 7                       # dry run assigned nothing for real
    res = assign_run(db, BACKFILL_SOURCE, "T3", apply=True)
    assert res["assigned_now"] == 7 and res["still_unassigned"] == 0 and sum(res["per_agent"].values()) == 7
    with SessionLocal() as s:
        mine = s.query(Order).filter(Order.external_order_id.like("csv:delta:%")).all()
        rep = [o for o in mine if o.customer_id == next(x.customer_id for x in mine if x.external_order_id == "csv:delta:101")]
        assert len(rep) == 2 and len({o.assigned_agent_id for o in rep}) == 1 and all("[VERIFY - SAME CUSTOMER]" in o.call_note for o in rep)
        assert all(o.call_status == "NEW" for o in mine)
        assert all(s.query(OrderAssignment).filter(OrderAssignment.order_id == o.id).count() == 1 for o in mine)
    again = assign_run(db, BACKFILL_SOURCE, "T3", apply=True)                              # retry: nothing new
    assert again["assigned_now"] == 0 and again["skipped_already_assigned"] == 7
    with SessionLocal() as s: assert s.query(OrderAssignment).join(Order, Order.id == OrderAssignment.order_id).filter(Order.external_order_id.like("csv:delta:%")).count() == 7
    k1 = kp()
    for k in ("leads", "called", "confirmed", "confirmation_rate"): assert k1[k] == k0[k], k
    assert k1["backfilled_leads"] == k0["backfilled_leads"] + 7
    p = client.get('/api/v1/profit/dashboard?range=today').json()
    assert p["backfilled_leads"] >= 7 and p["kpi_population"]["leads_confirmed_cpa"] == "acquisition_only"
    db.close()


def test_backfill_orders_work_through_the_api_and_the_agent_queue_with_price_flag_visible(client):
    from app.api.routes import orders as R
    _, pids = _world(client, "CBF-1", "CBF-2")
    agent_ids = _agents(pids)
    sp = [spec("e.csv", "epsilon", {"CSV-SKU": "CBF-1"})]
    texts = {"e.csv": csv_text(("CSV-SKU", "Eps Normal", "212751000001", "Fes", 1, 199, "p", 501), ("CSV-SKU", "Eps Odd Price", "212762000002", "Rabat", 2, 349, "p", 502))}
    db = SessionLocal()
    backfill_run(db, texts, "T4", apply=True, include=set(), specs=sp)
    assign_run(db, BACKFILL_SOURCE, "T4", apply=True)
    # Orders API: list/search/detail return the new source and the flag text
    page = client.get('/api/v1/orders/paginated?limit=50&offset=0&search=Eps').json()
    items = page["items"] if isinstance(page, dict) and "items" in page else page
    mine = [o for o in items if o.get("source") == BACKFILL_SOURCE]
    assert len(mine) == 2 and all(o["call_status"] == "NEW" and o["assigned_agent_id"] for o in mine)
    odd = next(o for o in mine if o["external_order_id"] == "csv:epsilon:502")
    detail = client.get(f"/api/v1/orders/{odd['id']}").json()
    assert detail["source"] == BACKFILL_SOURCE and float(detail["total_price"]) == 349.0 and detail["quantity"] == 2
    assert "MUST verify the price with the customer BEFORE confirming or dispatching" in detail["call_note"]
    normal = next(o for o in mine if o["external_order_id"] == "csv:epsilon:501")
    assert "MUST verify" not in client.get(f"/api/v1/orders/{normal['id']}").json()["call_note"]
    # the assigned agent sees each order in the normal calling queue and the agent workspace board
    with SessionLocal() as s:
        for o in mine:
            agent = s.query(User).filter(User.id == o["assigned_agent_id"]).one()
            q = {x["id"] for x in R.my_queue(bucket="NEW", limit=200, db=s, user=agent)}
            board = R.agent_board(bucket="NEW", product_id=None, search=None, limit=100, offset=0, db=s, user=agent)
            lst = next((v for v in (board.get("orders"), board.get("items"), board.get("rows")) if isinstance(v, list)), []) if isinstance(board, dict) else board
            assert o["id"] in q and o["id"] in {x["id"] if isinstance(x, dict) else x.id for x in lst}
    db.close()
