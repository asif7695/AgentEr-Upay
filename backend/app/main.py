"""AgentEr Upay API. Bundle is loaded ONCE at startup; DB is auto-seeded on first run."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import settings
from .db import Base, engine
from .errors import install_handlers
from .ml.model_store import get_bundle
from .routers import allocation, economics, admin, agents, core
from .seeding import seed
from .services.context import ledger

log = logging.getLogger("upay")


@asynccontextmanager
async def lifespan(_: FastAPI):
    res = seed(force=False)                 # no-op when the database already exists
    if res.get("seeded"):
        log.info("Seeded database: %s", res)
    get_bundle()                            # load the model bundle once
    Base.metadata.create_all(engine)        # adds tables introduced after the database was first seeded
    ledger.load()                           # immutable ledger cache (safe columns only)
    yield


app = FastAPI(title="AgentEr Upay API", version="1.0.0", lifespan=lifespan,
              description="Liquidity forecasting for upay MFS agents. SYNTHETIC DATA PROTOTYPE. Recommendations only.")
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])
install_handlers(app)
app.include_router(core.router)
app.include_router(agents.router)
app.include_router(admin.router)
app.include_router(economics.router)
app.include_router(allocation.router)
