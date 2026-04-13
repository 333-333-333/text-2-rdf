"""text2rdf — Convert natural language text to RDF/OWL knowledge graphs via AMR parsing.

Pipeline
--------
1. Sentence Split   — spaCy splits raw text into individual sentences.
2. AMR Parsing      — BART (amrlib) maps each sentence to an AMR semantic graph.
3. AMR → RDF/OWL    — py-amr2fred applies FRED ODPs to each AMR graph, yielding RDF triples.
4. Knowledge Graph   — All per-sentence triples are merged into a single unified graph.
5. Serialization     — rdflib writes the final graph to disk in the requested format.

All components are specialized NLP systems (no general-purpose LLMs).
See README.md for theoretical foundations and architecture details.
"""

import argparse
import sys
from pathlib import Path

import spacy
import amrlib
from py_amr2fred import Amr2fred, Glossary
from rdflib import Graph


# ---------------------------------------------------------------------------
# Namespace URI constants  (UC-001 Namespace Registry, OQ-7)
# ---------------------------------------------------------------------------
# OQ-7: These URIs come from the UC-001 spec's Namespace Registry table.
# They MUST be verified against actual py-amr2fred output at integration time.
# In particular, amrb:, pblr:, vn.role:, quant:, fschema:, framester:,
# boxer:, and boxing: URIs need confirmation (see TASK-001-006).

NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
NS_OWL = "http://www.w3.org/2002/07/owl#"
NS_SCHEMA = "http://schema.org/"
NS_DUL = "http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#"
NS_PBLR = "http://www.ontologydesignpatterns.org/vn/vnframes/VerbNetRoles/"
NS_VN_ROLE = "http://www.ontologydesignpatterns.org/vn/vnframes/VerbNetRoles/"
NS_QUANT = "http://www.ontologydesignpatterns.org/ont/fred/quantifiers.owl#"
# amrb: URI is marked as "to be verified" in the spec (OQ-7).
# The value below is a placeholder — update after running TASK-001-006.
NS_AMRB = "https://docs.google.com/spreadsheets/d/1tLYnZfVJ6i9gYIsUBHVBGFCbaJIYtNOpLkTdGft8e50/edit#gid=0"
NS_FRAMESTER = "https://w3id.org/framester/"
NS_FSCHEMA = "https://w3id.org/framester/schema/"
NS_BOXER = "http://www.ontologydesignpatterns.org/ont/boxer/boxer.owl#"
NS_BOXING = "http://www.ontologydesignpatterns.org/ont/boxer/boxing.owl#"
NS_WN = "http://www.ontologydesignpatterns.org/ont/wn/wn30/"
NS_WD = "http://www.wikidata.org/entity/"

# Full URIs for specific predicates/types used in Level 1 permitted set
RDF_TYPE_URI = NS_RDF + "type"  # L1-P1
SCHEMA_NAME_URI = NS_SCHEMA + "name"  # L1-P7


# ---------------------------------------------------------------------------
# Ontology complexity level data structures  (UC-001 BR-1, BR-2, BR-3, BR-7)
# ---------------------------------------------------------------------------
#
# Level 1 — Simple ontology (~40% of triples): INCLUSION list
#   Only triples whose predicate matches one of the explicitly permitted
#   patterns (L1-P1 through L1-P8) are retained.  Unrecognized predicates
#   are excluded by default (BR-7 strict mode).
#
# Level 2 — Intermediate ontology (~75% of triples): EXCLUSION list
#   All triples are retained *except* those whose predicate or object
#   falls in an explicitly excluded namespace.  Unrecognized predicates
#   pass through (BR-7 permissive mode).
#
# Level 3 — Complete ontology (100% of triples): PASSTHROUGH
#   No filtering is applied.  This is the default and must remain
#   byte-identical to pre-feature output (BR-3, BR-6).

# ---------------------------------------------------------------------------
# Level 1 — Permitted predicate rules  (BR-1, L1-P1 through L1-P8)
# ---------------------------------------------------------------------------
#
# The inclusion list uses three matching strategies:
#   1. LEVEL_1_PERMITTED_PREDICATE_EXACT   — exact URI equality
#   2. LEVEL_1_PERMITTED_PREDICATE_PREFIXES — URI starts-with (for wildcards)
#   3. LEVEL_1_PERMITTED_PREDICATE_VN_ROLES — exact URIs for vn.role predicates
#
# A predicate is permitted at Level 1 if it matches ANY of these three sets.
#
# L1-P1: rdf:type        — permitted (but object must also pass excluded-type check)
# L1-P2: pblr:*          — all PropBank local roles
# L1-P3: vn.role:Location
# L1-P4: vn.role:Time
# L1-P5: vn.role:Theme
# L1-P6: vn.role:Agent
# L1-P7: schema:name     — literal names
# L1-P8: amrb:*          — date/AMR-specific literals

# Predicates matched by exact URI
LEVEL_1_PERMITTED_PREDICATE_EXACT: set[str] = {
    RDF_TYPE_URI,  # L1-P1: rdf:type (object still checked against excluded types)
    SCHEMA_NAME_URI,  # L1-P7: schema:name — literal names
}

# Predicates matched by namespace prefix (URI starts with)
LEVEL_1_PERMITTED_PREDICATE_PREFIXES: set[str] = {
    NS_PBLR,  # L1-P2: pblr:* — PropBank local roles
    NS_AMRB,  # L1-P8: amrb:* — date/AMR-specific predicates
}

# Specific vn.role predicates matched by exact URI  (L1-P3 to L1-P6)
LEVEL_1_PERMITTED_PREDICATE_VN_ROLES: set[str] = {
    NS_VN_ROLE + "Location",  # L1-P3: vn.role:Location
    NS_VN_ROLE + "Time",  # L1-P4: vn.role:Time
    NS_VN_ROLE + "Theme",  # L1-P5: vn.role:Theme
    NS_VN_ROLE + "Agent",  # L1-P6: vn.role:Agent
}

# ---------------------------------------------------------------------------
# Level 1 — Excluded object types for rdf:type  (BR-1, BR-5)
# ---------------------------------------------------------------------------
# When a triple has predicate rdf:type, the object is checked against these
# namespace prefixes.  If the object URI starts with one of these prefixes,
# the triple is excluded even though rdf:type itself is a permitted predicate.
# This blocks OWL metamodel declarations (e.g. ?x rdf:type owl:Restriction)
# while retaining domain-level typing (e.g. ?x rdf:type pblr:run-01).

LEVEL_1_EXCLUDED_RDF_TYPE_OBJECT_PREFIXES: set[str] = {
    NS_OWL,  # owl:Restriction, owl:Class, owl:NamedIndividual, etc.
    NS_FRAMESTER,  # framester:* — cross-ontology classification
    NS_FSCHEMA,  # fschema:* / VerbAtlas — cross-ontology classification
    NS_WN,  # wn:* — WSD/WordNet synset types
    NS_WD,  # wd:* — Wikidata types
}

# ---------------------------------------------------------------------------
# Level 2 — Excluded predicate namespaces  (BR-2)
# ---------------------------------------------------------------------------
# Level 2 uses an exclusion list: predicates NOT in these namespaces pass
# through.  Unrecognized predicates are included (BR-7 permissive mode).
# WSD disambiguation (wn:* and Wikidata/wd:*) is also excluded.

LEVEL_2_EXCLUDED_PREDICATE_PREFIXES: set[str] = {
    NS_OWL,  # owl:* — all OWL predicates (equivalentClass, disjointWith, etc.)
    NS_FRAMESTER,  # framester:* — cross-ontology linking (subsumedUnder, etc.)
    NS_FSCHEMA,  # fschema:* — VerbAtlas cross-ontology linking
    NS_WN,  # wn:* — WSD/WordNet synset links
    NS_WD,  # wd:* — Wikidata links (typically via owl:sameAs)
}

# ---------------------------------------------------------------------------
# Level 2 — Excluded object types for rdf:type  (BR-2)
# ---------------------------------------------------------------------------
# Same excluded object-type namespaces as Level 1 (BR-2 states "same as L1").

LEVEL_2_EXCLUDED_RDF_TYPE_OBJECT_PREFIXES: set[str] = (
    LEVEL_1_EXCLUDED_RDF_TYPE_OBJECT_PREFIXES
)

# ---------------------------------------------------------------------------
# Level 3 — No filtering  (BR-3)
# ---------------------------------------------------------------------------
# Level 3 retains all triples from py-amr2fred output.  No data structures
# are needed — the filter function simply returns the graph unchanged.
# This is the default and must be byte-identical to pre-feature output (BR-6).


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse and return command-line arguments.

    Default input is ``input.txt`` and default output is ``output.rdf``.
    The ``--no-postprocess`` flag is accepted for backward compatibility but
    currently has no effect — the wikimapper post-processing path is not yet
    wired into the conversion loop.  See the note on the zombie flag below.
    """
    parser = argparse.ArgumentParser(
        description="Convert natural language text to RDF/OWL via AMR parsing.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("input.txt"),
        help="Input text file (default: input.txt)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output.rdf"),
        help="Output RDF file (default: output.rdf)",
    )
    parser.add_argument(
        "--format",
        choices=["turtle", "xml", "n3", "nt"],
        default="turtle",
        help="RDF serialization format (default: turtle)",
    )
    # UC-001 Main Flow Step 2: --level selects ontology complexity level.
    # Default is 3 for backward compatibility (BR-6). Invalid values are
    # rejected by argparse with choices validation (EF-1).
    parser.add_argument(
        "--level",
        type=int,
        choices=[1, 2, 3],
        default=3,
        help="Ontology complexity level: 1=simple (~40%% triples), 2=intermediate (~75%%), 3=complete (default)",
    )
    # NOTE (zombie flag): --no-postprocess is accepted for CLI backward
    # compatibility but is not yet consumed by any conversion logic.
    # The intended behaviour is to skip wikimapper enrichment (avoiding the
    # ~832 MB DB download), but that code path has not been implemented.
    # Remove or wire it up once post-processing is integrated.
    parser.add_argument(
        "--no-postprocess",
        action="store_true",
        help="Skip wikimapper post-processing (currently unused — no effect)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Text I/O helpers
# ---------------------------------------------------------------------------


def load_text(path: Path) -> str:
    """Read and return the UTF-8 content of *path*, stripped of leading/trailing whitespace.

    Raises:
        FileNotFoundError: If *path* does not exist on disk.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def split_sentences(text: str, nlp) -> list[str]:
    """Use a spaCy model to split *text* into non-empty sentence strings.

    # spaCy determines sentence boundaries from local patterns (punctuation,
    # nearby syntactic dependencies). Each split decision is made with
    # immediate context only, without requiring global document information.
    """
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents if sent.text.strip()]


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


def load_models(rdf_format: str):
    """Load all NLP models and return ``(nlp, amr_parser, amr2fred, rdf_mode)``.

    * *nlp*        — spaCy ``en_core_web_sm`` for sentence splitting.
    * *amr_parser* — amrlib STOG model for text → AMR conversion.
    * *amr2fred*   — py-amr2fred instance for AMR → RDF/OWL via FRED ODPs.
    * *rdf_mode*   — ``Glossary.RdflibMode`` enum matching *rdf_format*.
    """
    nlp = spacy.load("en_core_web_sm")
    amr_parser = amrlib.load_stog_model()
    amr2fred = Amr2fred()
    rdf_mode = _amr_to_rdflib_mode(rdf_format)
    return nlp, amr_parser, amr2fred, rdf_mode


def _amr_to_rdflib_mode(fmt: str):
    """Map a CLI format string to a ``Glossary.RdflibMode`` enum value."""
    mapping = {
        "turtle": Glossary.RdflibMode.TURTLE,
        "xml": Glossary.RdflibMode.XML,
        "n3": Glossary.RdflibMode.N3,
        "nt": Glossary.RdflibMode.NT,
    }
    return mapping[fmt]


# ---------------------------------------------------------------------------
# AMR parsing
# ---------------------------------------------------------------------------


def parse_to_amr(sentences: list[str], amr_parser) -> list[str]:
    """Parse each sentence into an AMR graph string using the STOG model.

    # Each sentence is converted to AMR in isolation. The BART model infers
    # semantic structure (concepts, PropBank roles, relations) exclusively
    # from the tokens of that individual sentence, with no access to
    # preceding or following sentences. The meaning of each node and edge
    # is deduced from the lexical surface of the source sentence alone.

    Returns:
        A list of AMR strings in PENMAN notation (one per sentence).
        Empty strings indicate sentences that could not be parsed.
    """
    print("Parsing AMR...")
    amr_graphs = amr_parser.parse_sents(sentences)
    return amr_graphs


# ---------------------------------------------------------------------------
# AMR → RDF conversion
# ---------------------------------------------------------------------------


def amr_to_rdf(amr_string: str, amr2fred: Amr2fred, rdf_mode) -> Graph | None:
    """Convert a single AMR graph to an RDF graph via FRED-style ODPs.

    # py-amr2fred translates the AMR graph to RDF triples by applying
    # Ontology Design Patterns (ODPs) over the concepts and roles of
    # that individual representation. Deductions — event type,
    # participant instantiation, ontological alignment (DUL, PropBank,
    # WordNet) — are inferred exclusively from that sentence's AMR,
    # without consulting graphs from other sentences.

    Args:
        amr_string: AMR graph in PENMAN notation.
        amr2fred:   Initialized py-amr2fred converter.
        rdf_mode:   ``Glossary.RdflibMode`` enum (affects amr2fred internals).

    Returns:
        An ``rdflib.Graph`` with the extracted triples, or ``None`` if
        conversion fails.
    """
    try:
        turtle_string = amr2fred.translate(
            amr_string,
            serialize=True,
            mode=rdf_mode,
        )
        # Paradox: amr2fred always outputs Turtle regardless of rdf_mode,
        # so we must always parse as "turtle" here.  The user's chosen
        # format is only applied during final serialization.
        sentence_graph = Graph()
        sentence_graph.parse(data=turtle_string, format="turtle")
        return sentence_graph
    except Exception as exc:
        print(
            f"  Error during AMR→RDF conversion: {exc}", file=__import__("sys").stderr
        )
        return None


# ---------------------------------------------------------------------------
# Knowledge graph construction
# ---------------------------------------------------------------------------


def build_knowledge_graph(
    sentences: list[str],
    amr_graphs: list[str],
    amr2fred: Amr2fred,
    rdf_mode,
) -> tuple[Graph, int, int]:
    """Merge per-sentence RDF graphs into a single knowledge graph.

    # Merging individual triples into a shared graph is a cross-sentence
    # inference operation. By sharing a common URI namespace (generated by
    # py-amr2fred seeded with Discourse Representation Theory), nodes that
    # represent the same entity across different sentences are automatically
    # unified when added to the same ``rdflib.Graph``. This is equivalent to
    # resolving cross-references: if "She" in sentence 3 and "Mary" in
    # sentence 1 produce the same URI, their triples link together without
    # explicit coreference resolution. The coherence of the resulting graph
    # depends on the consistency of the identifiers generated by amr2fred,
    # which constitutes a form of distributed inference: knowledge emerges
    # from the aggregation of per-sentence inferences.

    Args:
        sentences:   Original sentence strings (for progress logging).
        amr_graphs:  AMR PENMAN strings (one per sentence; empty = parse failure).
        amr2fred:    Initialized py-amr2fred converter.
        rdf_mode:    ``Glossary.RdflibMode`` enum.

    Returns:
        ``(knowledge_graph, parsed_ok, parse_failures)`` where
        *parsed_ok* counts sentences successfully converted and
        *parse_failures* counts sentences that were skipped.
    """
    print("Converting AMR → RDF...")
    knowledge_graph = Graph()
    parsed_ok = 0
    parse_failures = 0

    for idx, amr_string in enumerate(amr_graphs, start=1):
        if not amr_string:
            print(f"  [{idx}/{len(sentences)}] skipped (empty AMR)")
            parse_failures += 1
            continue

        sentence_graph = amr_to_rdf(amr_string, amr2fred, rdf_mode)

        if sentence_graph is None:
            print(f"  [{idx}/{len(sentences)}] skipped (conversion error)")
            parse_failures += 1
            continue

        knowledge_graph += sentence_graph
        print(
            f"  [{idx}/{len(sentences)}] {len(sentence_graph):>4} triples"
            f" — {sentences[idx - 1][:60]}"
        )
        parsed_ok += 1

    return knowledge_graph, parsed_ok, parse_failures


# ---------------------------------------------------------------------------
# Ontology complexity filtering  (UC-001 BR-1 through BR-7)
# ---------------------------------------------------------------------------


def _uri_starts_with_any(uri: str, prefixes: set[str]) -> bool:
    """Return True if *uri* starts with any string in *prefixes*."""
    return any(uri.startswith(prefix) for prefix in prefixes)


def _is_predicate_permitted_level1(predicate_uri: str) -> bool:
    """Check whether a predicate URI is in the Level 1 permitted set.

    A predicate is permitted at Level 1 if it matches **any** of:
    - An exact URI in ``LEVEL_1_PERMITTED_PREDICATE_EXACT``, OR
    - A namespace prefix in ``LEVEL_1_PERMITTED_PREDICATE_PREFIXES``, OR
    - An exact URI in ``LEVEL_1_PERMITTED_PREDICATE_VN_ROLES``

    Unrecognized predicates are excluded by default (BR-7 strict mode).
    """
    return (
        predicate_uri in LEVEL_1_PERMITTED_PREDICATE_EXACT
        or _uri_starts_with_any(predicate_uri, LEVEL_1_PERMITTED_PREDICATE_PREFIXES)
        or predicate_uri in LEVEL_1_PERMITTED_PREDICATE_VN_ROLES
    )


def _is_object_excluded_for_rdf_type(
    object_uri: str, excluded_prefixes: set[str]
) -> bool:
    """Check whether an ``rdf:type`` object URI falls in an excluded namespace (BR-5).

    This implements the dual evaluation for ``rdf:type``: even though
    ``rdf:type`` is a permitted predicate, the triple is excluded if the
    object's URI starts with one of the excluded object-type namespace
    prefixes.
    """
    return _uri_starts_with_any(object_uri, excluded_prefixes)


def apply_complexity_filter(graph: Graph, level: int) -> Graph:
    """Filter RDF graph based on ontology complexity level.

    Level 1 (Simple): Uses INCLUSION list — only explicitly permitted
    predicates pass (BR-1, BR-7 strict).

    Level 2 (Intermediate): Uses EXCLUSION list — only explicitly
    excluded predicates are blocked (BR-2, BR-7 permissive).

    Level 3 (Complete): No filtering — returns the graph unchanged (BR-3).

    For ``rdf:type`` triples at Levels 1 and 2, an additional object-type
    check is applied (BR-5): the triple is excluded if the object URI
    starts with one of the level's Excluded Object Type namespace prefixes,
    even though ``rdf:type`` itself is a permitted predicate.

    Args:
        graph: Input RDF graph to filter.
        level: Complexity level (1, 2, or 3).

    Returns:
        Filtered graph.  The input graph is **not** mutated.

    Raises:
        ValueError: If *level* is not 1, 2, or 3.
    """
    # UC-001 BR-3: Level 3 — passthrough, no filtering applied.
    # Return the same graph object (no copy needed since nothing is modified).
    # This guarantees byte-identical output for AC-4 / BR-6 backward compatibility.
    if level == 3:
        return graph

    if level not in (1, 2):
        raise ValueError(f"Invalid complexity level {level!r}; must be 1, 2, or 3.")

    result = Graph()

    if level == 1:
        # UC-001 BR-1: Level 1 — inclusion list (strict mode, BR-7)
        # Only triples whose predicate matches L1-P1 through L1-P8 are retained.
        for s, p, o in graph:
            if _is_predicate_permitted_level1(str(p)):
                # UC-001 BR-5: Dual evaluation for rdf:type —
                # exclude if the object is in an excluded object-type namespace.
                if str(p) == RDF_TYPE_URI and _is_object_excluded_for_rdf_type(
                    str(o), LEVEL_1_EXCLUDED_RDF_TYPE_OBJECT_PREFIXES
                ):
                    continue
                result.add((s, p, o))
            # Unrecognized predicates are excluded (BR-7 strict mode).

    elif level == 2:
        # UC-001 BR-2: Level 2 — exclusion list (permissive mode, BR-7)
        # All triples are retained except those explicitly excluded.
        for s, p, o in graph:
            p_str = str(p)
            # Exclude if the predicate falls in an excluded namespace.
            if _uri_starts_with_any(p_str, LEVEL_2_EXCLUDED_PREDICATE_PREFIXES):
                continue
            # UC-001 BR-5: Dual evaluation for rdf:type —
            # exclude if the object is in an excluded object-type namespace.
            if p_str == RDF_TYPE_URI and _is_object_excluded_for_rdf_type(
                str(o), LEVEL_2_EXCLUDED_RDF_TYPE_OBJECT_PREFIXES
            ):
                continue
            result.add((s, p, o))
            # Unrecognized predicates pass through (BR-7 permissive mode).

    # UC-001 EF-3: Warn if filter removed all triples from the graph.
    if len(result) == 0:
        print(
            "Warning: complexity filter removed all triples from the graph.",
            file=sys.stderr,
        )

    return result


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_output(
    graph: Graph,
    output_path: Path,
    rdf_format: str,
    parsed_ok: int,
    parse_failures: int,
) -> None:
    """Serialize *graph* to *output_path* in the requested format and print a summary.

    Args:
        graph:          The merged RDF knowledge graph.
        output_path:    Destination file path.
        rdf_format:     Serialization format string (``turtle``, ``xml``, ``n3``, ``nt``).
        parsed_ok:      Count of sentences successfully converted.
        parse_failures: Count of sentences that failed or were skipped.
    """
    graph.serialize(str(output_path), format=rdf_format)

    print("\nDone.")
    print(f"  Sentences : {parsed_ok} ok, {parse_failures} skipped")
    print(f"  Triples   : {len(graph)}")
    print(f"  Output    : {output_path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Orchestrate the full text → RDF pipeline.

    1. Parse CLI arguments.
    2. Load NLP models (spaCy, amrlib, py-amr2fred).
    3. Read and sentence-split the input text.
    4. Parse each sentence into AMR.
    5. Convert each AMR graph to RDF triples and merge into a knowledge graph.
    6. Serialize the final graph to the output file.
    """
    args = parse_args()

    # 1. Load models
    nlp, amr_parser, amr2fred, rdf_mode = load_models(args.format)

    # 2. Read input
    text = load_text(args.input)
    print(f"Input : {args.input} ({len(text)} chars)")

    # 3. Sentence splitting
    sentences = split_sentences(text, nlp)
    print(f"Sentences detected: {len(sentences)}")

    # 4. AMR parsing
    amr_graphs = parse_to_amr(sentences, amr_parser)

    # 5. Build knowledge graph
    knowledge_graph, parsed_ok, parse_failures = build_knowledge_graph(
        sentences,
        amr_graphs,
        amr2fred,
        rdf_mode,
    )

    # 6. Serialize output
    serialize_output(
        knowledge_graph, args.output, args.format, parsed_ok, parse_failures
    )


if __name__ == "__main__":
    main()
