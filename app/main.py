from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, engine
from .routers import accounts, auth, budgets, goals, imports, summary, sync, transactions

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Finsathi API",
    version="1.0.0",
    description="Backend for Finsathi: auth, accounts, transactions, budgets, goals and bank-statement import.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_origin_regex=None,
    allow_credentials=False,  # we use Bearer tokens, not cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, accounts.router, transactions.router, budgets.router, goals.router, imports.router, summary.router, sync.router):
    app.include_router(r, prefix="/api")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/", tags=["meta"])
def root():
    return {"name": "Finsathi API", "docs": "/docs", "health": "/health"}
