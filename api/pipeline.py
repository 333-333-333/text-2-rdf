"""Pipeline wrapper — bridges the FastAPI layer with src/text2rdf.py.

The pipeline is NOT thread-safe (py-amr2fred uses singletons internally).
All calls are serialized through a threading.Lock.

Models are loaded once at import time in a background thread so that
the FastAPI server can bind its port immediately.
"""

import io
import sys
import threading
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

# Add src/ to sys.path so we can import text2rdf as a bare module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text2rdf import (
    apply_complexity_filter,
    build_knowledge_graph,
    load_models,
    parse_to_amr,
    split_sentences,
)

# ---------------------------------------------------------------------------
# Content-Type mapping for RDF serialization formats
# ---------------------------------------------------------------------------

CONTENT_TYPE_MAP: dict[str, str] = {
    "turtle": "text/turtle",
    "xml": "application/rdf+xml",
    "n3": "text/n3",
    "nt": "text/plain",
}


class PipelineService:
    """Thread-safe wrapper around the text2rdf pipeline.

    Usage::

        svc = PipelineService()          # starts background model loading
        svc.wait_until_ready()           # blocks until models loaded
        result = svc.process("Hello.")   # returns RDF string
    """

    def __init__(self) -> None:
        self._nlp = None
        self._amr_parser = None
        self._amr2fred = None
        self._rdf_mode = None
        self._ready = False
        self._error: str | None = None
        self._lock = threading.Lock()
        self._ready_event = threading.Event()

        # Start model loading in a daemon thread so the caller can proceed
        # (e.g. start the HTTP server) without blocking.
        self._loader_thread = threading.Thread(target=self._load_models, daemon=True)
        self._loader_thread.start()

    # ------------------------------------------------------------------
    # Internal: background model loading
    # ------------------------------------------------------------------

    def _load_models(self) -> None:
        """Load all NLP models. Runs in a background thread."""
        try:
            with (
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                self._nlp, self._amr_parser, self._amr2fred, self._rdf_mode = (
                    load_models("turtle")
                )
            self._ready = True
        except Exception as exc:
            self._error = str(exc)
        finally:
            self._ready_event.set()

    def wait_until_ready(self, timeout: float | None = None) -> None:
        """Block until models are loaded (or loading fails).

        Args:
            timeout: Max seconds to wait (None = wait forever).
        """
        self._ready_event.wait(timeout=timeout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        """Return ``True`` when models have been loaded successfully."""
        return self._ready

    @property
    def load_error(self) -> str | None:
        """Return the error message if model loading failed, else ``None``."""
        return self._error

    def process(
        self,
        text: str,
        rdf_format: str = "turtle",
        level: int = 3,
    ) -> str:
        """Run the full text → AMR → RDF pipeline and return the serialized string.

        Args:
            text:        Input natural-language text.
            rdf_format:  Serialization format (``turtle``, ``xml``, ``n3``, ``nt``).
            level:       Ontology complexity level (1, 2, or 3).

        Returns:
            RDF graph serialized as a string.

        Raises:
            RuntimeError:  If models are not yet loaded.
            RuntimeError:  If the pipeline produced an empty graph.
            ValueError:    If *rdf_format* or *level* is invalid.
        """
        if not self._ready:
            raise RuntimeError("Models are still loading or failed to load.")
        if rdf_format not in CONTENT_TYPE_MAP:
            raise ValueError(
                f"Invalid format {rdf_format!r}; must be one of {list(CONTENT_TYPE_MAP)}"
            )
        if level not in (1, 2, 3):
            raise ValueError(f"Invalid level {level!r}; must be 1, 2, or 3.")

        # Serialize all pipeline calls through a lock — py-amr2fred singletons
        # are NOT thread-safe (see engram obs #398).
        with self._lock, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            # Step 1: Sentence splitting
            sentences = split_sentences(text, self._nlp)

            # Step 2: AMR parsing
            amr_graphs = parse_to_amr(sentences, self._amr_parser)

            # Step 3: AMR → RDF / knowledge graph construction
            graph, parsed_ok, parse_failures = build_knowledge_graph(
                sentences,
                amr_graphs,
                self._amr2fred,
                self._rdf_mode,
            )

            # Step 4: Apply complexity filter
            graph = apply_complexity_filter(graph, level)

        # Step 5: Serialize to requested format
        serialized = graph.serialize(format=rdf_format)
        if not serialized:
            raise RuntimeError(
                "Pipeline produced an empty result. "
                f"Parsed {parsed_ok} sentence(s), {parse_failures} failure(s)."
            )
        return serialized


# ---------------------------------------------------------------------------
# Singleton instance — created once at module import time.
# ---------------------------------------------------------------------------

pipeline_service = PipelineService()
