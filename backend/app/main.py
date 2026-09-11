from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import aggregator, cases, checks, orders

settings = get_settings()

app = FastAPI(title="ResolveX API", version="0.1.0")

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
