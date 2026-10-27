from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": error.detail},
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        # Never echo input values: request bodies can contain passwords.
        details = [
            {
                "field": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
            }
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": "Please check your details.", "details": details},
        )
