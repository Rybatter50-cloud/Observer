"""
RYBAT Intelligence Platform - Entity Screening API Routes
==========================================================
REST endpoints for screening named entities against FBI, Interpol,
and OpenSanctions databases.

Endpoints:
  POST /api/v1/screening/check     — screen a name against all sources
  GET  /api/v1/screening/status    — service health / cache info

2026-02-12 | Mr Cat + Claude
"""

from typing import Optional, List
from dataclasses import asdict
from datetime import datetime, timedelta
import csv
import io

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.entity_screening import get_screening_service
from utils.logging import get_logger

logger = get_logger(__name__)

screening_router = APIRouter(prefix="/api/v1/screening", tags=["screening"])


# ── Request / Response models ──

class ScreeningRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=200, description="Name to screen")
    sources: Optional[List[str]] = Field(
        None,
        description="Sources to check: 'fbi', 'interpol', 'opensanctions'. Default: all available."
    )
    entity_type: str = Field(
        'Person',
        description="Entity type for OpenSanctions: 'Person' or 'Organization'"
    )
    signal_id: Optional[int] = Field(None, description="Associated signal ID (for tracking)")


class ScreeningHitResponse(BaseModel):
    source: str
    name: str
    score: float
    category: str
    details: dict = {}
    url: Optional[str] = None


class ScreeningResponse(BaseModel):
    query: str
    hit_count: int
    max_score: float
    sources_checked: List[str]
    sources_failed: List[str]
    elapsed_ms: float
    hits: List[ScreeningHitResponse]


# ── Endpoints ──

@screening_router.post("/check", response_model=ScreeningResponse)
async def screen_entity(request: ScreeningRequest, raw_request: Request):
    """
    Screen a named entity against FBI, Interpol, and OpenSanctions.
    Returns scored hits from each source.
    """
    try:
        service = get_screening_service()

        # Validate sources if provided
        valid_sources = {'fbi', 'interpol', 'opensanctions', 'sanctions_network'}
        if request.sources:
            invalid = set(request.sources) - valid_sources
            if invalid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid sources: {', '.join(invalid)}. Valid: {', '.join(valid_sources)}"
                )

        result = await service.screen_entity(
            name=request.name,
            sources=request.sources,
            entity_type=request.entity_type,
        )

        # Log the screening check with client IP
        try:
            repo = service.opensanctions._repo
            if repo:
                client_ip = raw_request.headers.get('x-forwarded-for', '').split(',')[0].strip()
                if not client_ip:
                    client_ip = raw_request.client.host if raw_request.client else 'unknown'
                await repo.log_screening(
                    queried_name=request.name,
                    hit_count=result.hit_count,
                    sources_checked=result.sources_checked,
                    client_ip=client_ip,
                )
        except Exception as log_err:
            logger.warning(f"Failed to log screening check: {log_err}")

        return ScreeningResponse(
            query=result.query,
            hit_count=result.hit_count,
            max_score=result.max_score,
            sources_checked=result.sources_checked,
            sources_failed=result.sources_failed,
            elapsed_ms=result.elapsed_ms,
            hits=[
                ScreeningHitResponse(
                    source=h.source,
                    name=h.name,
                    score=h.score,
                    category=h.category,
                    details=h.details,
                    url=h.url,
                )
                for h in result.hits
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Screening error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@screening_router.get("/log/recent")
async def screening_log_recent():
    """Return the 15 most recent screening log entries."""
    try:
        from api.deps import db

        entries = await db.screening.get_recent_screenings(limit=15)
        return {"entries": entries}
    except Exception as e:
        logger.error(f"Screening log error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@screening_router.get("/status")
async def screening_status():
    """Get screening service status and cache info."""
    try:
        service = get_screening_service()
        return await service.get_status()
    except Exception as e:
        logger.error(f"Screening status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Report generation ──

class ReportRequest(BaseModel):
    date_start: str = Field(..., description="ISO date string YYYY-MM-DD")
    date_end: str = Field(..., description="ISO date string YYYY-MM-DD")
    sources: List[str] = Field(default_factory=lambda: ["fbi", "interpol", "opensanctions", "sanctions_network"])
    format: str = Field(default="summary", description="summary or detailed")


async def _query_report_entries(date_start: str, date_end: str, sources: List[str]):
    """Fetch screening log entries within a date range, optionally filtered by source."""
    from api.deps import db

    start_dt = datetime.fromisoformat(date_start)
    end_dt = datetime.fromisoformat(date_end) + timedelta(days=1)  # inclusive

    rows = await db.screening.get_recent_screenings(limit=10000)

    entries = []
    for row in rows:
        created = row.get('created_at')
        if not created:
            continue
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        if created < start_dt or created >= end_dt:
            continue

        row_sources = (row.get('sources_checked') or '').split(',')
        row_sources = [s.strip() for s in row_sources if s.strip()]

        if sources:
            if not any(s in row_sources for s in sources):
                continue

        entries.append(row)

    return entries


@screening_router.post("/report")
async def generate_screening_report(req: ReportRequest):
    """Generate an aggregated screening report for the given date range and sources."""
    try:
        entries = await _query_report_entries(req.date_start, req.date_end, req.sources)

        total_hits = sum(e.get('hit_count', 0) for e in entries)
        unique_names = len(set(e.get('queried_name', '') for e in entries))
        unique_ips = len(set(e.get('client_ip', '') for e in entries))

        by_source: dict[str, int] = {}
        for e in entries:
            for src in (e.get('sources_checked') or '').split(','):
                src = src.strip()
                if src:
                    by_source[src] = by_source.get(src, 0) + 1

        result = {
            "total_checks": len(entries),
            "total_hits": total_hits,
            "unique_names": unique_names,
            "unique_ips": unique_ips,
            "by_source": by_source,
            "date_start": req.date_start,
            "date_end": req.date_end,
        }

        if req.format == "detailed":
            result["entries"] = entries

        return result

    except Exception as e:
        logger.error(f"Report generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@screening_router.get("/report/export")
async def export_screening_report_csv(date_start: str, date_end: str, sources: str = ""):
    """Export screening report as CSV download."""
    try:
        source_list = [s.strip() for s in sources.split(',') if s.strip()] if sources else []
        entries = await _query_report_entries(date_start, date_end, source_list)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Time", "Name", "Hits", "Sources", "IP"])
        for e in entries:
            writer.writerow([
                e.get('created_at', ''),
                e.get('queried_name', ''),
                e.get('hit_count', 0),
                e.get('sources_checked', ''),
                e.get('client_ip', ''),
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=screening_report_{date_start}_{date_end}.csv"},
        )

    except Exception as e:
        logger.error(f"Report CSV export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
