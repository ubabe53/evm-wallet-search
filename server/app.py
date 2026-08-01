"""FastAPI application serving complete DuckDB analytics through bounded queries."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from scripts.artifact_paths import LIVE_DB_PATH
from server.queries import (
    ACCOUNT_FILTERS,
    DEFAULT_WALLET_ADDRESS,
    DashboardFilters,
    DatabaseUnavailable,
    InvalidCursor,
    InvalidTokenAddress,
    QueryService,
    TokenNotFound,
)


class AccountFilter(str, Enum):
    none = "none"
    eoa_candidate = "eoa_candidate"
    contract = "contract"


class RecognitionFilter(str, Enum):
    all = "all"
    recognized = "recognized"
    other = "other"


class TimelineInterval(str, Enum):
    month = "month"
    year = "year"


class RecognitionOverrideRequest(BaseModel):
    status: Literal["recognized", "other"]


def dashboard_filters(
    wallet_address: str = DEFAULT_WALLET_ADDRESS,
    recognition: RecognitionFilter = RecognitionFilter.all,
    account: Annotated[list[AccountFilter] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
    start: date | None = None,
    end: date | None = None,
) -> DashboardFilters:
    if account and AccountFilter.none in account:
        if len(account) != 1:
            raise HTTPException(status_code=422, detail="account=none cannot be combined with other account filters")
        selected = ()
    else:
        selected = tuple(item.value for item in account) if account else ACCOUNT_FILTERS
    if (start is None) != (end is None):
        raise HTTPException(status_code=422, detail="start and end must be provided together")
    if start is not None and end is not None and start >= end:
        raise HTTPException(status_code=422, detail="start must be before exclusive end")
    normalized_query = q.strip() if q and q.strip() else None
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", wallet_address):
        raise HTTPException(status_code=422, detail="wallet_address must be a 20-byte hexadecimal address")
    return DashboardFilters(
        account_filters=selected,
        wallet_address=wallet_address.lower(),
        query=normalized_query,
        recognition=recognition.value,
        start_at=datetime.combine(start, time.min, timezone.utc) if start else None,
        end_before=datetime.combine(end, time.min, timezone.utc) if end else None,
    )


def create_app(service: QueryService | None = None) -> FastAPI:
    query_service = service or QueryService(LIVE_DB_PATH)
    application = FastAPI(
        title="EVM Wallet Search API",
        version="1.0.0",
        description="Complete calculations and local token-recognition overrides over the live DuckDB artifact.",
    )

    @application.exception_handler(DatabaseUnavailable)
    async def database_unavailable(_request, error: DatabaseUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @application.exception_handler(InvalidTokenAddress)
    async def invalid_token_address(_request, error: InvalidTokenAddress) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @application.exception_handler(TokenNotFound)
    async def token_not_found(_request, error: TokenNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.get("/api/v1/health")
    def health() -> dict:
        metadata = query_service.metadata()
        return {
            "status": "ok",
            "data_source": metadata["data_source"],
            "generated_at": metadata["generated_at"],
            "api_schema_version": metadata["api_schema_version"],
        }

    @application.get("/api/v1/metadata")
    def metadata(wallet_address: str = DEFAULT_WALLET_ADDRESS) -> dict:
        return query_service.metadata(wallet_address.lower())

    @application.get("/api/v1/summary")
    def summary(filters: Annotated[DashboardFilters, Depends(dashboard_filters)]) -> dict:
        return query_service.summary(filters)

    @application.get("/api/v1/events")
    def events(
        filters: Annotated[DashboardFilters, Depends(dashboard_filters)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: str | None = None,
    ) -> dict:
        try:
            return query_service.events(filters, limit=limit, cursor=cursor)
        except InvalidCursor as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.get("/api/v1/tokens")
    def tokens(
        filters: Annotated[DashboardFilters, Depends(dashboard_filters)],
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict:
        return query_service.tokens(filters, limit=limit)

    @application.put("/api/v1/tokens/{token_address}/recognition")
    def set_token_recognition(token_address: str, request: RecognitionOverrideRequest) -> dict:
        return query_service.set_token_recognition(token_address, request.status)

    @application.delete("/api/v1/tokens/{token_address}/recognition")
    def reset_token_recognition(token_address: str) -> dict:
        return query_service.reset_token_recognition(token_address)

    @application.get("/api/v1/timeline")
    def timeline(
        filters: Annotated[DashboardFilters, Depends(dashboard_filters)],
        interval: TimelineInterval = TimelineInterval.year,
        year: Annotated[int | None, Query(ge=1970, le=9999)] = None,
    ) -> dict:
        if interval is TimelineInterval.month and year is None:
            raise HTTPException(status_code=422, detail="year is required for monthly timeline buckets")
        if interval is TimelineInterval.year and year is not None:
            raise HTTPException(status_code=422, detail="year is only valid for monthly timeline buckets")
        return query_service.timeline(filters, interval=interval.value, year=year)

    @application.get("/api/v1/counterparties")
    def counterparties(
        filters: Annotated[DashboardFilters, Depends(dashboard_filters)],
        limit: Annotated[int, Query(ge=1, le=100)] = 10,
    ) -> dict:
        return query_service.counterparties(filters, limit=limit)

    return application


app = create_app()
