import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .ml.eta_model import eta_model
from .ml.fault_model import fault_model
from .routers import aggregator, assistant, cases, checks, orders, workflow, demo, ops_map, commerce, rider_join

settings = get_settings()

# Vercel freezes an instance once it responds, so the polling thread would never
# tick there no matter how the setting is configured.
RUN_DEMO_WORKER = settings.enable_demo_worker and not os.environ.get("VERCEL")


@asynccontextmanager
async def lifespan(app: FastAPI):
    eta_model.load(settings.eta_model_path)
    fault_model.load(settings.fault_model_path)
    if RUN_DEMO_WORKER:
        demo.start_worker()
    yield
    demo.STOP.set()


app = FastAPI(title="ResolveX API", version="0.1.0", lifespan=lifespan)


@app.get("/api/model/status")
def model_status() -> dict:
    return {**fault_model.status(), **eta_model.status()}


configured_origins = [
    origin.strip().rstrip("/")
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]

origin_patterns = [r"https?://(localhost|127\.0\.0\.1)(:\d+)?"]
if settings.cors_origin_regex:
    origin_patterns.append(settings.cors_origin_regex)
origin_regex = "^(" + "|".join(origin_patterns) + ")$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(commerce.router)
app.include_router(rider_join.router)
app.include_router(cases.router)
app.include_router(checks.router)
app.include_router(aggregator.router)
app.include_router(assistant.router)
app.include_router(orders.router)
app.include_router(workflow.router)
app.include_router(demo.router)
app.include_router(ops_map.router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "cors_origins": configured_origins,
        "cors_origin_regex": origin_regex,
    }
