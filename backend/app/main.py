from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.endpoints import portfolio, recommendations, runs, theses, transactions, watchlist
from app.core.config import get_settings
from app.core.redis import close_redis_pool
from app.core.run_logging import configure_logging, log_event
from app.core.security import limiter

configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event(logger, logging.INFO, 'api_starting', service='swing-scout-api')
    yield
    await close_redis_pool()
    log_event(logger, logging.INFO, 'api_stopped', service='swing-scout-api')


app = FastAPI(title='SwingScout API', lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

allowed_origins = ['http://localhost:5173']
if settings.frontend_url and settings.frontend_url not in allowed_origins:
    allowed_origins.append(settings.frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
def health_check():
    return {'status': 'ok', 'service': 'SwingScout API'}


app.include_router(portfolio.router, prefix='/api/portfolio', tags=['Portfolio'])
app.include_router(transactions.router, prefix='/api/transactions', tags=['Transactions'])
app.include_router(theses.router, prefix='/api/theses', tags=['Theses'])
app.include_router(runs.router, prefix='/api/runs', tags=['Runs'])
app.include_router(recommendations.router, prefix='/api/recommendations', tags=['Recommendations'])
app.include_router(watchlist.router, prefix='/api/watchlist', tags=['Watchlist'])
