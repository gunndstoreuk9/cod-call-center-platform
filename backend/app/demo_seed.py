"""Optional demo dataset for previewing the bilingual UI.
Run manually: python -m app.demo_seed
Never runs automatically in production.
"""
from datetime import timedelta
from decimal import Decimal

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.core.time import utcnow
from app.models import AgentProduct, Customer, DeliveryShipment, Order, PayoutEntry, Product, Store, User


def seed_demo():
    db = SessionLocal()
    try:
        if db.query(Order).filter(Order.order_number == "DEMO-001").first():
            print("Demo data already exists; nothing changed.")
            return
        store = db.query(Store).filter(Store.code == "MOROCCO").first()
        if not store:
            store = Store(name="Morocco Store", code="MOROCCO", country="MA", currency="MAD", timezone="Africa/Casablanca")
            db.add(store); db.flush()

        specs = [
            ("DEMO-NOVAMAN", "NOVAMAN", Decimal("399"), Decimal("5")),
            ("DEMO-BSC", "Blood Sugar Complex", Decimal("299"), Decimal("6")),
        ]
        products=[]
        for sku,name,price,commission in specs:
            p=db.query(Product).filter(Product.sku==sku).first()
            if not p:
                p=Product(store_id=store.id,name=name,sku=sku,selling_price=price,currency="MAD",default_qty=1,delivery_product_ref=name,commission_per_confirmation=commission,status="ACTIVE")
                db.add(p); db.flush()
            products.append(p)

        agents=[]
        for username,display in [("demo.sara","Sara Demo"),("demo.amine","Amine Demo")]:
            a=db.query(User).filter(User.username==username).first()
            if not a:
                a=User(username=username,password_hash=hash_password("DemoPass123!"),display_name=display,role="AGENT",is_active=True,commission_default=Decimal("5"))
                db.add(a); db.flush()
            agents.append(a)
            for p in products:
                if not db.query(AgentProduct).filter_by(agent_id=a.id,product_id=p.id).first(): db.add(AgentProduct(agent_id=a.id,product_id=p.id))

        names=["Youssef A.","Salma B.","Hamza C.","Imane D.","Omar E.","Sara F.","Mehdi G.","Nadia H.","Ayoub I.","Meryem J."]
        cities=["Casablanca","Rabat","Marrakech","Agadir","Tangier"]
        statuses=[
            ("NEW","NOT_READY"),("NO_ANSWER","NOT_READY"),("CALLBACK","NOT_READY"),
            ("CONFIRMED","DISPATCHED"),("CONFIRMED","IN_TRANSIT"),("CONFIRMED","DELIVERED"),
            ("CONFIRMED","DELIVERED"),("CONFIRMED","REFUSED"),("CANCELLED","NOT_READY")
        ]
        now=utcnow()
        for i in range(1,31):
            p=products[i%2]; a=agents[i%2]; call_status,delivery_status=statuses[i%len(statuses)]
            phone=f"+21260000{i:04d}"
            c=Customer(name=names[i%len(names)],phone_raw=phone,phone_e164=phone,city=cities[i%len(cities)],address=f"Demo address {i}, {cities[i%len(cities)]}")
            db.add(c); db.flush()
            created=now-timedelta(hours=i*2 if i<16 else 28+(i-16)*2)
            confirmed_at=created+timedelta(minutes=6) if call_status=="CONFIRMED" else None
            delivered_at=created+timedelta(hours=20) if delivery_status=="DELIVERED" else None
            o=Order(order_number=f"DEMO-{i:03d}",store_id=store.id,product_id=p.id,customer_id=c.id,assigned_agent_id=a.id,quantity=1,unit_price=p.selling_price,total_price=p.selling_price,currency="MAD",source="DEMO",call_status=call_status,delivery_status=delivery_status,city=c.city,address=c.address,assigned_at=created+timedelta(minutes=1),first_call_at=created+timedelta(minutes=3),confirmed_at=confirmed_at,dispatched_at=(confirmed_at+timedelta(minutes=3) if confirmed_at and delivery_status!="NOT_READY" else None),delivered_at=delivered_at,created_at=created,updated_at=created)
            db.add(o); db.flush()
            if call_status=="CONFIRMED":
                commission=p.commission_per_confirmation or a.commission_default
                db.add(PayoutEntry(agent_id=a.id,order_id=o.id,product_id=p.id,entry_type="CONFIRMATION",amount=commission,status="UNPAID",description="Demo confirmation commission",created_at=confirmed_at or created))
            if delivery_status in {"DISPATCHED","IN_TRANSIT","DELIVERED","REFUSED"}:
                db.add(DeliveryShipment(order_id=o.id,provider="DIGYLOG",external_id=f"DG-DEMO-{i:03d}",tracking_number=f"DGDEMO{i:05d}",external_status_id=6 if delivery_status=="DELIVERED" else 9 if delivery_status=="REFUSED" else 1,status=delivery_status,cod_amount=o.total_price,destination_city=o.city,delivery_fee=Decimal("35"),delivered_at=delivered_at,last_synced_at=created+timedelta(hours=1),created_at=created))
        db.commit()
        print("Demo dataset created: 2 products, 2 agents, 30 orders.")
        print("Demo agent login: demo.sara / DemoPass123! (change/remove before production).")
    finally:
        db.close()

if __name__ == "__main__":
    seed_demo()
