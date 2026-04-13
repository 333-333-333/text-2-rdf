"""FastAPI application for the text-2-rdf HTTP API.

Endpoints
---------
- ``POST /v1/to-rdf``   — convert text to RDF
- ``GET  /health``      — readiness probe
"""

import asyncio
from enum import Enum
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from api.pipeline import CONTENT_TYPE_MAP, pipeline_service

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="text-2-rdf API",
    version="1.0.0",
    description="Convert natural-language text to RDF/OWL knowledge graphs via AMR parsing.",
)

# CORS — allow the frontend container to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:80"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RdfFormat(str, Enum):
    """Supported RDF serialization formats."""

    turtle = "turtle"
    xml = "xml"
    n3 = "n3"
    nt = "nt"


class ToRdfRequest(BaseModel):
    """Request body for ``POST /v1/to-rdf``."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Natural-language text to convert (max 5000 chars).",
    )
    format: RdfFormat = Field(
        default=RdfFormat.turtle,
        description="RDF serialization format.",
    )
    level: Literal[1, 2, 3] = Field(
        default=3,
        description="Ontology complexity level: 1=simple, 2=intermediate, 3=complete.",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Return service readiness status.

    - ``{"status": "ready"}``   — models loaded, accepting requests.
    - ``503 {"status": "loading"}`` — models still loading.
    """
    if pipeline_service.is_ready:
        return {"status": "ready"}
    error = pipeline_service.load_error
    status_msg = "loading"
    if error:
        status_msg = f"loading (error: {error})"
    raise HTTPException(status_code=503, detail={"status": status_msg})


@app.post("/v1/to-rdf", response_class=PlainTextResponse)
async def to_rdf(body: ToRdfRequest):
    """Convert natural-language text to an RDF knowledge graph.

    The pipeline runs synchronously in a thread-pool executor because the
    underlying NLP models (spaCy, amrlib, py-amr2fred) are not async-safe.
    """
    if not pipeline_service.is_ready:
        raise HTTPException(
            status_code=503,
            detail="Models are still loading. Try again shortly.",
        )

    rdf_format = body.format.value

    try:
        result = await asyncio.to_thread(
            pipeline_service.process,
            text=body.text,
            rdf_format=rdf_format,
            level=body.level,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc

    return PlainTextResponse(
        content=result,
        media_type=CONTENT_TYPE_MAP[rdf_format],
    )
