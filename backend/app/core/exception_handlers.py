import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import VoyagerError

logger = logging.getLogger(__name__)

def add_exception_handlers(app: FastAPI):
    @app.exception_handler(VoyagerError)
    async def voyager_error_handler(request: Request, exc: VoyagerError):
        logger.warning(
            f"VoyagerError: {exc.message}",
            extra={"status_code": exc.status_code, "details": exc.details}
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.message,
                    "details": exc.details
                }
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning("Validation error on request", extra={"errors": exc.errors()})
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "message": "Validation Error",
                    "details": exc.errors()
                }
            }
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        logger.warning(f"HTTPException: {exc.detail}", extra={"status_code": exc.status_code})
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.detail
                }
            }
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled server error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "message": "Internal Server Error"
                }
            }
        )
