from contextlib import asynccontextmanager

from fastapi import FastAPI
from .ml.fault_model import fault_model
from .ml.eta_model import eta_model
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import aggregator, cases, checks, orders

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    eta_model.load(settings.eta_model_path)
    fault_model.load(settings.fault_model_path)
    yield


app = FastAPI(title="ResolveX API", version="0.1.0", lifespan=lifespan)


@app.get("/api/model/status")
def model_status() -> dict:
    return {**fault_model.status(), **eta_model.status()}


app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases.router)
app.include_router(checks.router)
app.include_router(aggregator.router)
app.include_router(orders.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
