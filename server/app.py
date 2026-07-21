"""FastAPI application serving complete DuckDB analytics through bounded queries."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from scripts.artifact_paths import LIVE_DB_PATH
from server.queries import (
    ACCOUNT_FILTERS,
    DashboardFilters,
    DatabaseUnavailable,
    InvalidCursor,
    QueryService,
)


class AccountFilter(str, Enum):
    none = "none"
    eoa_candidate = "eoa_candidate"
    contract = "contract"


def dashboard_filters(
    include_spam: bool = False,
    account: Annotated[list[AccountFilter] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
) -> DashboardFilters:
    if account and AccountFilter.none in account:
        if len(account) != 1:
            raise HTTPException(status_code=422, detail="account=none cannot be combined with other account filters")
        selected = ()
    else:
        selected = tuple(item.value for item in account) if account else ACCOUNT_FILTERS
    normalized_query = q.strip() if q and q.strip() else None
    return DashboardFilters(include_spam, selected, normalized_query)


def create_app(service: QueryService | None = None) -> FastAPI:
    query_service = service or QueryService(LIVE_DB_PATH)
    application = FastAPI(
        title="EVM Wallet Search API",
        version="1.0.0",
        description="Read-only, complete calculations over the live DuckDB analytics artifact.",
    )

    @application.exception_handler(DatabaseUnavailable)
    async def database_unavailable(_request, error: DatabaseUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

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
    def metadata() -> dict:
        return query_service.metadata()

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

    @application.get("/api/v1/counterparties")
    def counterparties(
        filters: Annotated[DashboardFilters, Depends(dashboard_filters)],
        limit: Annotated[int, Query(ge=1, le=100)] = 10,
    ) -> dict:
        return query_service.counterparties(filters, limit=limit)

    @application.get("/api/v1/graph")
    def graph(
        filters: Annotated[DashboardFilters, Depends(dashboard_filters)],
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> dict:
        return query_service.graph(filters, limit=limit)

    return application


app = create_app()
