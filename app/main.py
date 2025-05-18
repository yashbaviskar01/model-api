import os
import sys
import warnings
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.routes import routes
from app.routes import prompt_routes  # Newly created router

request_id_header = "X-Request-ID"

warnings.filterwarnings("ignore", category=UserWarning)

# def initialize_logger():
#     logger_format = (
#         "{time:YYYY-MM-DD HH:mm:ss.SSS} |{level: <7}| "
#         "{name}:{function}:{line} | {message}"
#     )
#     logger.remove()

#     logs_folder = "logs"
#     os.makedirs(logs_folder, exist_ok=True)

#     file_path = (
#         f"{logs_folder}/"
#         f"{datetime.now().strftime('%Y-%m-%d')}/"
#         f"{datetime.now().strftime('%H-%M')}.log"
#     )
#     os.makedirs(os.path.dirname(file_path), exist_ok=True)

#     logger.add(
#         sink=file_path,
#         rotation="2 MB",
#         retention="10 days",
#         format=logger_format,
#         level="DEBUG",
#         enqueue=True
#     )
#     return logger


def initialize_logger():
    """Initialize Loguru logger with configurable level."""

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} |{level:<7}| {extra[request_id]} | "
        "{name}:{function}:{line} | {message}"
    )

    logger.remove()
    logger.add(
        sys.stdout,
        format=logger_format,
        level=log_level,
        enqueue=True,
    )

    # Add default value for request_id so format doesn't fail
    logger = logger.bind(request_id="-")
    return logger



# 1) Instantiate the logger
logger = initialize_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("App is starting up...")
    try:
        yield
    except Exception as e:
        logger.info(f"App is about to crash! Error: {e}")
        raise
    finally:
        logger.info("App is shutting down...")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get(request_id_header, str(uuid4()))
    request.state.request_id = request_id
    with logger.bind(request_id=request_id):
        logger.info(f"Incoming request: {request.method} {request.url.path}")
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Unhandled error: {exc}")
            raise
        logger.info(
            f"Completed request {request.method} {request.url.path} with status {response.status_code}"
        )
        return response

app.include_router(routes.router)
app.include_router(prompt_routes.router)

logger.info("FastAPI app is running.")
