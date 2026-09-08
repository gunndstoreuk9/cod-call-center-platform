import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.services.demo_auto_scheduler import (
    demo_auto_scheduler_loop,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()

    scheduler_task = asyncio.create_task(
        demo_auto_scheduler_loop(
            stop_event
        )
    )

    app.state.demo_auto_scheduler_stop = (
        stop_event
    )

    app.state.demo_auto_scheduler_task = (
        scheduler_task
    )

    try:
        yield

    finally:
        stop_event.set()

        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": settings.app_name,
        "environment": settings.environment,
    }
