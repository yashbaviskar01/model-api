import os
import sys
import warnings
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
from app.routes import routes
from app.routes import prompt_routes  # Newly created router

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
    logger_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} |{level: <7}| "
        "{name}:{function}:{line} | {message}"
    )
    # Remove all existing sinks
    logger.remove()

    # Add a new sink that logs to standard output
    logger.add(
        sys.stdout,
        format=logger_format,
        level="DEBUG",
        enqueue=True
    )
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

app.include_router(routes.router)
app.include_router(prompt_routes.router)

logger.info("FastAPI app is running.")
