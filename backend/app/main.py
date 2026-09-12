from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .ml.eta_model import eta_model
from .ml.fault_model import fault_model
from .routers import aggregator, assistant, cases, checks, orders, workflow, demo, ops_map, commerce

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    eta_model.load(settings.eta_model_path)
    fault_model.load(settings.fault_model_path)
    demo.start_worker()
    yield
    demo.STOP.set()


app = FastAPI(title="ResolveX API", version="0.1.0", lifespan=lifespan)


@app.get("/api/model/status")
def model_status() -> dict:
    return {**fault_model.status(), **eta_model.status()}


# Keep explicitly configured production origins, while always allowing local
# Vite development from either hostname. This avoids localhost vs 127.0.0.1
# mismatches and also works when Vite selects a different local port.
configured_origins = [
    origin.strip().rstrip("/")
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(commerce.router)
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
    }
