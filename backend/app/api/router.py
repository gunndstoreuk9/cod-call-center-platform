from fastapi import APIRouter
from app.api.routes import agents, analytics, auth, callbacks, connections, delivery, integrations, orders, payments, products, profit, stores

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(stores.router)
api_router.include_router(products.router)
api_router.include_router(agents.router)
api_router.include_router(orders.router)
api_router.include_router(callbacks.router)
api_router.include_router(connections.router)

api_router.include_router(integrations.router)
api_router.include_router(delivery.router)
api_router.include_router(payments.router)
api_router.include_router(analytics.router)

api_router.include_router(profit.router)
