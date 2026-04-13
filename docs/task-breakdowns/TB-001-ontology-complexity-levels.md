# Task Breakdown: UC-001-ontology-complexity-levels

## Overview
- **Total tasks:** 6
- **Estimated phases:** 3
- **Parallelizable tasks:** TASK-001-001 and TASK-001-002 can run concurrently (no shared dependency)

## Phase 1: Foundation — Data Structures & CLI

These tasks have no cross-dependencies and can be developed in parallel.

### TASK-001-001: Define complexity level constants and data structures
- **Type:** backend
- **Spec reference:** BR-1 (Level 1 permitted/excluded sets), BR-2 (Level 2 permitted/excluded sets), BR-3 (Level 3 = no filter), BR-7 (unrecognized predicate handling), Namespace Registry table
- **Description:** Create a Python module (or section within `text2rdf.py`) that defines all data structures encoding the complexity level rules. This includes:
  1. A dictionary or class mapping each level (1, 2, 3) to its filtering strategy — inclusion list for Level 1, exclusion list for Level 2, passthrough for Level 3.
  2. Level 1 **permitted predicate** set: URIs for `rdf:type`, `pblr:*`, `vn.role:Location`, `vn.role:Time`, `vn.role:Theme`, `vn.role:Agent`, `schema:name`, `amrb:*` date predicates (L1-P1 through L1-P8).
  3. Level 1 **excluded object types** for `rdf:type`: namespace URIs for `owl:*`, `framester:*`, `fschema:*`, `wn:*`, `wd:*`.
  4. Level 2 **excluded predicate** namespaces: `owl:*`, `framester:*`, `fschema:*`, WSD (`wn:*`, `wd:*` via `owl:sameAs`).
  5. Level 2 **excluded object types** for `rdf:type`: same as Level 1.
  6. Namespace URI constants for all prefixes in the Namespace Registry (must be verified against actual py-amr2fred output per OQ-7).
- **Acceptance criteria:**
  1. All 15 namespace URIs from the spec's Namespace Registry are defined as Python constants.
  2. Level 1 permitted predicate set contains exactly the 8 rules L1-P1 through L1-P8, expressed as namespace URI patterns matchable against full predicate URIs.
  3. Level 1 excluded object-type namespaces include `owl:`, `framester:`, `fschema:`, `wn:`, `wd:`.
  4. Level 2 excluded predicate namespaces include `owl:`, `framester:`, `fschema:`, plus WSD-specific exclusions.
  5. Level 3 strategy is defined as passthrough (no filtering).
  6. A comment or docstring references OQ-7, noting that URIs must be verified against real py-amr2fred output at integration time.
- **Dependencies:** none
- **Files likely affected:** `src/text2rdf.py` (new constants section after imports)

### TASK-001-002: Add `--level` CLI argument to `parse_args()`
- **Type:** backend
- **Spec reference:** Main Flow steps 1–2, AF-1 (default to 3), BR-6 (backward compatibility), EF-1 (invalid level rejection)
- **Description:** Extend the `parse_args()` function to accept a `--level` argument with `choices=[1, 2, 3]`, `type=int`, `default=3`. This ensures argparse rejects invalid values (EF-1) with a built-in error message and non-zero exit. The default of 3 guarantees backward compatibility (BR-6, AC-1). Also update the module docstring and `--no-postprocess` help text to note that levels 1–2 naturally exclude WSD/Wikidata content (AF-2, AF-3).
- **Acceptance criteria:**
  1. `parse_args()` accepts `--level 1`, `--level 2`, `--level 3` and returns `args.level` as an `int`.
  2. When `--level` is omitted, `args.level == 3` (AC-1, BR-6).
  3. `--level 0`, `--level 4`, `--level foo` each cause argparse to print an error and exit with non-zero status (AC-9, EF-1).
  4. `--no-postprocess` flag still accepted without error (AC-12).
  5. `--no-postprocess` together with `--level` accepted without error (AF-2).
- **Dependencies:** none
- **Files likely affected:** `src/text2rdf.py` (`parse_args()` function, module docstring)

---

## Phase 2: Core Filtering Logic

### TASK-001-003: Implement `apply_complexity_filter()` function
- **Type:** backend
- **Spec reference:** BR-1 (Level 1 inclusion logic), BR-2 (Level 2 exclusion logic), BR-3 (Level 3 passthrough), BR-4 (post-generation only), BR-5 (dual evaluation for `rdf:type`), BR-7 (unrecognized predicate handling), EF-3 (empty graph warning)
- **Description:** Implement the core filtering function with signature `apply_complexity_filter(graph: Graph, level: int) -> Graph`. The function:
  1. Returns the graph unchanged when `level == 3` (BR-3).
  2. For Level 1: iterates over a snapshot (`list(graph)`), keeps only triples whose predicate matches one of L1-P1 through L1-P8. For `rdf:type` triples, additionally checks that the object URI is not in the L1 Excluded Object Types set (BR-5). All unrecognized predicates are excluded (BR-7, strict mode).
  3. For Level 2: iterates over a snapshot, removes triples whose predicate falls in an excluded namespace. For `rdf:type` triples, additionally removes if the object is in the L2 Excluded Object Types set. Unrecognized predicates pass through (BR-7, permissive mode).
  4. Uses `graph.remove(triple)` on a snapshot, not while iterating directly (Technical Notes).
  5. Returns a **new** filtered `Graph` (does not mutate the input graph — safer for testing and debugging). Alternatively, mutates a copy. Decision: return a new graph to preserve the original.
  6. If the result has zero triples, prints warning to **stderr**: `"Warning: complexity filter removed all triples from the graph."` (EF-3, AC-10).
- **Acceptance criteria:**
  1. `apply_complexity_filter(graph, 3)` returns a graph with identical triple count and content to the input (AC-4).
  2. `apply_complexity_filter(graph, 1)` produces a graph containing only triples whose predicates match L1-P1 through L1-P8, with `rdf:type` object filtering applied (AC-2, AC-5, AC-13, AC-14, AC-16).
  3. `apply_complexity_filter(graph, 2)` produces a graph with no `owl:`, `framester:`, `fschema:`, WSD predicates; all other predicates pass through (AC-3, AC-6, AC-7, AC-11, AC-15, AC-17).
  4. When filtering removes all triples, a warning is printed to **stderr** and a valid empty graph is returned (AC-10, EF-3).
  5. The input graph is not mutated by the function.
  6. Level 1 uses an **inclusion list** approach (only explicitly permitted predicates pass) (BR-7, Technical Notes).
  7. Level 2 uses an **exclusion list** approach (only explicitly excluded predicates/namespaces are blocked) (BR-7, Technical Notes).
- **Dependencies:** TASK-001-001 (consumes the level data structures)
- **Files likely affected:** `src/text2rdf.py` (new function between `build_knowledge_graph()` and `serialize_output()`)

---

## Phase 3: Integration & Validation

### TASK-001-004: Integrate filter into `main()` pipeline
- **Type:** backend
- **Spec reference:** Main Flow steps 7–11, BR-4 (filtering after generation, before serialization), Postcondition 1 (output contains only permitted triples), Postcondition 5 (summary reports post-filter triple count)
- **Description:** Wire the complexity filter into `main()` between `build_knowledge_graph()` and `serialize_output()`. Pass `args.level` to the filter. Update the pipeline so that:
  1. After `build_knowledge_graph()` returns, call `apply_complexity_filter(knowledge_graph, args.level)` to get the filtered graph.
  2. Pass the **filtered** graph to `serialize_output()`, ensuring the summary triple count reflects post-filter state (Postcondition 5).
  3. The per-sentence triple counts printed during `build_knowledge_graph()` remain pre-filter (as specified in Technical Notes — they come from `amr_to_rdf`).
  4. Update `main()` docstring to document the new step 6 (filtering) and step 7 (serialization of filtered graph).
- **Acceptance criteria:**
  1. `main()` calls `apply_complexity_filter()` between `build_knowledge_graph()` and `serialize_output()` (Main Flow steps 8–10).
  2. `serialize_output()` receives the filtered graph, so `len(graph)` in the summary reflects the post-filter triple count (Postcondition 5).
  3. Running `text2rdf --input X --output Y` (no `--level`) produces byte-identical output to the pre-feature version (AC-1, AC-4, BR-6).
  4. Running `text2rdf --input X --output Y --level 1` produces a reduced graph (AC-2).
  5. Running `text2rdf --input X --output Y --level 2` produces a partially reduced graph (AC-3).
- **Dependencies:** TASK-001-002 (needs `args.level`), TASK-001-003 (needs `apply_complexity_filter()`)
- **Files likely affected:** `src/text2rdf.py` (`main()` function, `serialize_output()` signature if needed)

### TASK-001-005: Add unit tests for the complexity filter
- **Type:** backend
- **Spec reference:** All Acceptance Criteria (AC-1 through AC-17), all Business Rules (BR-1 through BR-7), Exception Flow EF-3
- **Description:** Create a test file `tests/test_complexity_filter.py` with unit tests covering:
  1. **Level 3 passthrough:** filter(graph, 3) returns identical graph (AC-1, AC-4, AC-8).
  2. **Level 1 inclusion logic:** only L1-P1 through L1-P8 predicates survive; unrecognized predicates excluded (AC-2, AC-5, AC-13, AC-14, AC-16).
  3. **Level 1 `rdf:type` object filtering:** `?x rdf:type owl:Restriction` excluded; `?x rdf:type pblr:run-01` retained (AC-13).
  4. **Level 2 exclusion logic:** `owl:`, `framester:`, `fschema:` predicates excluded; all others pass (AC-3, AC-6, AC-7, AC-11, AC-15, AC-17).
  5. **Level 2 `rdf:type` object filtering:** same excluded object types as Level 1 (AC-13).
  6. **Empty graph warning (EF-3):** when all triples removed, stderr contains warning, returned graph has 0 triples (AC-10).
  7. **CLI validation:** `--level` only accepts 1, 2, 3; invalid values rejected (AC-9, EF-1).
  8. **Default level:** omitting `--level` defaults to 3 (AC-1).
  9. **`--no-postprocess` compatibility:** flag accepted at any level (AC-12).
  10. **WSD/Wikidata exclusion at levels 1–2:** triples with `wn:*` or `wd:*` / `owl:sameAs` links excluded at levels 1 and 2 (AC-11).

  Tests should construct small `rdflib.Graph` instances with representative triples for each rule, rather than depending on py-amr2fred output (which requires heavy NLP models).
- **Acceptance criteria:**
  1. All 17 acceptance criteria from the spec have at least one corresponding test case.
  2. Tests run without requiring spaCy, amrlib, or py-amr2fred (use hand-crafted RDF graphs).
  3. `pytest tests/test_complexity_filter.py` passes with 0 failures.
  4. Test for EF-3 captures stderr output and asserts the warning message.
  5. Test for EF-1 uses `subprocess` or argparse's own validation to confirm non-zero exit on invalid `--level`.
- **Dependencies:** TASK-001-003 (needs `apply_complexity_filter()` function), TASK-001-002 (needs `--level` argument for CLI tests)
- **Files likely affected:** `tests/test_complexity_filter.py` (new file), `tests/__init__.py` (new file if needed)

### TASK-001-006: Verify namespace URIs against py-amr2fred output (OQ-7)
- **Type:** integration
- **Spec reference:** OQ-7, Namespace Registry table
- **Description:** Run py-amr2fred on a sample input and extract the actual namespace prefixes and URIs from the serialized Turtle output. Compare each URI constant defined in TASK-001-001 against the real output. Specifically verify:
  1. `amrb:` URI prefix (marked as "to be verified" in spec).
  2. `pblr:` URI prefix.
  3. `vn.role:` URI prefix.
  4. `quant:` URI prefix.
  5. `fschema:` URI prefix.
  6. `framester:` URI prefix.
  7. `boxer:` / `boxing:` URI prefixes.

  Update the Python constants if any URI differs from what the spec listed. Add a comment in code documenting the verification date and any discrepancies found.
- **Acceptance criteria:**
  1. Every namespace URI constant matches the actual URI produced by py-amr2fred (or is documented as a known discrepancy).
  2. A code comment records the verification date and method.
  3. If any URI was corrected, the change is documented in code and the task breakdown.
- **Dependencies:** TASK-001-001 (needs the constants to verify)
- **Files likely affected:** `src/text2rdf.py` (namespace URI constants section)

---

## Task Dependency Graph

```
TASK-001 ──→ TASK-003 ──→ TASK-004
TASK-002 ─────────────────→ TASK-004
TASK-003 ─────────────────→ TASK-005
TASK-002 ─────────────────→ TASK-005
TASK-001 ──→ TASK-006
```

**Parallelization details:**
- TASK-001-001 and TASK-001-002 can execute in parallel (no shared dependency).
- TASK-001-003 starts after TASK-001-001 completes.
- TASK-001-004 starts after both TASK-001-003 and TASK-001-002 complete.
- TASK-001-005 starts after TASK-001-003 and TASK-001-002 complete (can run in parallel with TASK-001-004).
- TASK-001-006 starts after TASK-001-001 and can run in parallel with TASK-001-003.

```
Phase 1 (parallel):
  TASK-001-001 ──┐
  TASK-001-002 ──┤
                 │
Phase 2:         │
  TASK-001-003 ←─┘ (depends on 001)
  TASK-001-006 ←── (depends on 001, parallel with 003)
                 │
Phase 3:         │
  TASK-001-004 ←── (depends on 002 + 003)
  TASK-001-005 ←── (depends on 002 + 003, parallel with 004)
```

---

## Summary of Spec-to-Task Traceability

| Spec Element | Covered by Task |
|---|---|
| Main Flow steps 1–2 | TASK-001-002 |
| Main Flow steps 3–7 | No change (existing pipeline) |
| Main Flow step 8 (apply filter) | TASK-001-003, TASK-001-004 |
| Main Flow step 9 (remove excluded triples) | TASK-001-003 |
| Main Flow step 10 (serialize filtered graph) | TASK-001-004 |
| Main Flow step 11 (summary with post-filter count) | TASK-001-004 |
| AF-1 (default level=3) | TASK-001-002 |
| AF-2 (--no-postprocess + --level) | TASK-001-002 |
| AF-3 (--no-postprocess alone) | TASK-001-002 |
| EF-1 (invalid level) | TASK-001-002, TASK-001-005 |
| EF-3 (empty graph warning) | TASK-001-003, TASK-001-005 |
| BR-1 (Level 1 rules) | TASK-001-001, TASK-001-003 |
| BR-2 (Level 2 rules) | TASK-001-001, TASK-001-003 |
| BR-3 (Level 3 passthrough) | TASK-001-003 |
| BR-4 (post-generation filter) | TASK-001-003, TASK-001-004 |
| BR-5 (dual eval for rdf:type) | TASK-001-003 |
| BR-6 (default=3 backward compat) | TASK-001-002, TASK-001-004 |
| BR-7 (unrecognized predicates) | TASK-001-001, TASK-001-003 |
| AC-1 through AC-17 | TASK-001-005 |
| OQ-7 (namespace URI verification) | TASK-001-006 |
