# UC-001: Ontology Complexity Levels

## Metadata
- **Actor(s):** CLI User (developer or data engineer invoking text2rdf)
- **Priority:** high
- **Status:** draft
- **Created:** 2026-04-08
- **Updated:** 2026-04-08
- **Related UCs:** —

## Description
Allow the user to select an ontology complexity level when converting text to RDF, controlling how many triples are included in the output graph. Level 1 (Simple) produces a minimal ontology with core entities and events; Level 2 (Intermediate) adds upper-ontology qualities, quantifiers, and structural patterns; Level 3 (Complete) retains the full output including OWL metamodel and cross-ontology links. Filtering is applied **after** py-amr2fred generates the full graph and **before** serialization, ensuring no modification to py-amr2fred internals.

## Namespace Registry

The following prefix-to-URI mappings are used throughout this specification. Implementors **MUST** verify these URIs against the actual py-amr2fred output at integration time (see OQ-7).

| Prefix | URI |
|--------|-----|
| `rdf:` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` |
| `rdfs:` | `http://www.w3.org/2000/01/rdf-schema#` |
| `owl:` | `http://www.w3.org/2002/07/owl#` |
| `schema:` | `http://schema.org/` |
| `dul:` | `http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#` |
| `pblr:` | `http://www.ontologydesignpatterns.org/vn/vnframes/VerbNetRoles/` |
| `vn.role:` | `http://www.ontologydesignpatterns.org/vn/vnframes/VerbNetRoles/` |
| `quant:` | `http://www.ontologydesignpatterns.org/ont/fred/quantifiers.owl#` |
| `amrb:` | *(to be verified against py-amr2fred output — see OQ-7)* |
| `framester:` | `https://w3id.org/framester/` |
| `fschema:` | `https://w3id.org/framester/schema/` |
| `boxer:` | `http://www.ontologydesignpatterns.org/ont/boxer/boxer.owl#` |
| `boxing:` | `http://www.ontologydesignpatterns.org/ont/boxer/boxing.owl#` |
| `wn:` | `http://www.ontologydesignpatterns.org/ont/wn/wn30/` |
| `wd:` | `http://www.wikidata.org/entity/` |

## Preconditions
1. The text2rdf CLI is installed and all NLP models (spaCy, amrlib, py-amr2fred) are available.
2. A valid input text file exists at the path specified by `--input`.
3. py-amr2fred can successfully generate the full (Level 3) RDF graph for the given input — filtering always starts from the complete output.

## Postconditions
1. The output RDF file contains only triples permitted by the selected complexity level.
2. The output graph is a valid, well-formed RDF graph serializable in the user's chosen format.
3. Level 3 output is byte-identical to the current (pre-feature) output for the same input, ensuring backward compatibility.
4. At Level 1 or Level 2, WSD/Wikidata post-processing triples are excluded (subsuming the `--no-postprocess` zombie flag behaviour).
5. The summary printed to stdout reports the actual triple count after filtering.

## Main Flow

1. **[Actor]** invokes text2rdf with `--level N` (where N ∈ {1, 2, 3}) along with standard arguments (`--input`, `--output`, `--format`).
2. **[System]** parses CLI arguments; if `--level` is omitted, defaults to 3.
3. **[System]** loads NLP models (spaCy, amrlib, py-amr2fred).
4. **[System]** reads the input file and splits it into sentences.
5. **[System]** parses each sentence into an AMR graph.
6. **[System]** converts each AMR graph to RDF via py-amr2fred, producing the **full** (Level 3) per-sentence graph.
7. **[System]** merges all per-sentence graphs into a single knowledge graph (current `build_knowledge_graph` behaviour).
8. **[System]** applies the complexity filter corresponding to the selected level (see Business Rules BR-1 through BR-7).
9. **[System]** removes triples not permitted at the selected level from the merged graph.
10. **[System]** serializes the filtered graph to the output file in the requested format.
11. **[System]** prints the summary (sentence counts, final triple count, output path).

## Alternative Flows

### AF-1: Level not specified (default to 3)
- **Branches from:** Main Flow step 1
- **Condition:** The `--level` flag is absent from the CLI invocation.
1. **[System]** sets `level = 3` internally.
2. Execution continues at Main Flow step 3.
- **Rejoins:** Main Flow step 3

### AF-2: `--no-postprocess` flag present together with `--level`
- **Branches from:** Main Flow step 2
- **Condition:** The user supplies both `--no-postprocess` and `--level`.
1. **[System]** accepts both flags without error.
2. **[System]** applies the `--level` filter (which already excludes WSD/Wikidata at levels 1 and 2). The `--no-postprocess` flag is effectively a no-op at levels 1–2 and redundant at level 3.
- **Rejoins:** Main Flow step 3

### AF-3: `--no-postprocess` flag present without `--level`
- **Branches from:** Main Flow step 2
- **Condition:** The user supplies `--no-postprocess` but not `--level`.
1. **[System]** sets `level = 3` (default).
2. **[System]** notes `--no-postprocess` for backward compatibility but does not change filtering behaviour (zombie flag — no effect).
- **Rejoins:** Main Flow step 3

## Exception Flows

### EF-1: Invalid level value
- **Triggers from:** Main Flow step 2
- **Condition:** The user provides `--level` with a value outside {1, 2, 3} (e.g., `--level 4` or `--level 0`).
1. **[System]** argparse validation rejects the value with an error message listing valid options.
2. **[System]** exits with non-zero status code.
- **Result:** No output file produced. Process terminates.

### EF-2: AMR parse failure for one or more sentences
- **Triggers from:** Main Flow step 6
- **Condition:** py-amr2fred raises an exception or returns an empty/unparseable result for a sentence.
1. **[System]** logs the error for that sentence (current behaviour in `amr_to_rdf`).
2. **[System]** skips the sentence and increments the failure counter.
3. Processing continues for remaining sentences.
- **Result:** Partial output graph (as per current behaviour). Filter is applied to whatever triples were successfully generated.

### EF-3: Filter produces empty graph
- **Triggers from:** Main Flow step 9
- **Condition:** After filtering, the knowledge graph contains zero triples (e.g., Level 1 applied to a graph consisting entirely of OWL metamodel triples).
1. **[System]** writes a warning to **stderr**: `"Warning: complexity filter removed all triples from the graph."`
2. **[System]** serializes the empty graph to the output file (zero-triple RDF is valid).
3. **[System]** prints the summary to stdout showing 0 triples.
- **Result:** Empty but valid output file.

## Business Rules

- **BR-1: Level 1 — Simple ontology (~40% of triples)**

  **Permitted predicate rules:**

  | Rule ID | Predicate pattern | Condition | Notes |
  |---------|-------------------|-----------|-------|
  | L1-P1 | `rdf:type` | Object must NOT be in the L1 Excluded Object Types set (see below) | Permits typing of event and entity instances; blocks OWL/cross-ontology metamodel typing |
  | L1-P2 | `pblr:*` | Unconditional | PropBank local roles |
  | L1-P3 | `vn.role:Location` | Unconditional | VerbNet location role |
  | L1-P4 | `vn.role:Time` | Unconditional | VerbNet temporal role |
  | L1-P5 | `vn.role:Theme` | Unconditional | VerbNet theme role (core semantic argument) |
  | L1-P6 | `vn.role:Agent` | Unconditional | VerbNet agent role (core semantic argument) |
  | L1-P7 | `schema:name` | Unconditional | Literal names |
  | L1-P8 | `amrb:year` and related `amrb:` date predicates | Unconditional | Date/AMR-specific literals |

  **L1 Excluded predicates** (triples with these predicates are always removed):

  - `owl:equivalentClass`, `owl:disjointWith`, and all other `owl:` predicates (note: `rdf:type` triples whose object is an `owl:` class are handled by the object-type rule below, not by this predicate exclusion)
  - `framester:subsumedUnder` and all other `framester:` predicates
  - `fschema:subsumedUnder` and all other `fschema:` predicates (VerbAtlas)
  - `dul:hasQuality`, `dul:hasDataValue`, `dul:hasMember`, `dul:precedes`, and all other `dul:` predicates
  - `quant:hasQuantifier` and all other `quant:` predicates
  - `rdfs:label`, `rdfs:subClassOf`, and all other `rdfs:` predicates
  - Reification pattern predicates: `cause-91`, `include-91`, `have-rel-role-91` (and any other `*-91` predicates)
  - `boxer:*` and `boxing:*` predicates (negation, modality — deferred to Level 2)
  - WSD disambiguation predicates: WordNet synset links (`wn:*`), Wikidata `owl:sameAs` links

  **L1 Excluded object types for `rdf:type`** (triples of the form `?s rdf:type ?o` are removed when `?o` matches):

  - `owl:Restriction`, `owl:Class`, `owl:NamedIndividual`, and any other `owl:` namespace type (these are OWL metamodel declarations, not domain typing)
  - `framester:*` types (cross-ontology classification)
  - `fschema:*` / VerbAtlas types (cross-ontology classification)
  - WSD/Wikidata types (`wn:*`, `wd:*`)

  **Unrecognized predicates** (see BR-7): Any predicate not matching L1-P1 through L1-P8 is excluded at Level 1.

- **BR-2: Level 2 — Intermediate ontology (~75% of triples)**

  Permitted: everything in Level 1 **plus**:

  | Rule ID | Predicate pattern | Condition | Notes |
  |---------|-------------------|-----------|-------|
  | L2-P1 | `dul:hasQuality`, `dul:hasDataValue`, `dul:hasMember`, `dul:precedes` | Unconditional | DUL quality/property triples |
  | L2-P2 | `quant:hasQuantifier` | Unconditional | Quantifier triples |
  | L2-P3 | `rdfs:label`, `rdfs:subClassOf` | Unconditional | RDFS structural triples |
  | L2-P4 | Reification predicates (`cause-91`, `include-91`, `have-rel-role-91`) | Unconditional | Reification pattern triples |
  | L2-P5 | `boxer:*` predicates | Unconditional | Negation and modality scope markers |
  | L2-P6 | `boxing:*` predicates | Unconditional | Negation and modality operators |

  **L2 Excluded predicates:**

  - `owl:equivalentClass`, `owl:disjointWith`, and all other `owl:` predicates
  - `framester:subsumedUnder` and all other `framester:` predicates
  - `fschema:subsumedUnder` and all other `fschema:` predicates (VerbAtlas)
  - WSD disambiguation predicates: WordNet synset links (`wn:*`), Wikidata `owl:sameAs` links

  **L2 Excluded object types for `rdf:type`:**

  - Same as L1: `owl:*` types, `framester:*` types, `fschema:*` / VerbAtlas types, WSD/Wikidata types

  **Unrecognized predicates** (see BR-7): Any predicate not explicitly excluded at Level 2 is **included** (permissive default). This means newly encountered or future py-amr2fred predicates pass through Level 2 unless they fall into an explicitly excluded namespace.

- **BR-3: Level 3 — Complete ontology (100% of triples)**
  Permitted: all triples generated by py-amr2fred. No filtering applied. This is the current behaviour and must remain byte-identical to pre-feature output.

- **BR-4: Filtering is post-generation only**
  py-amr2fred is always invoked with full output. The filter strips triples from the merged `rdflib.Graph` after generation, before serialization. py-amr2fred's `translate()` method is never modified or reconfigured.

- **BR-5: Filter operates on predicate with conditional object evaluation for `rdf:type`**
  The primary filter criterion is the predicate URI. A triple is excluded if its predicate belongs to an excluded namespace/predicate for the current level. **Exception:** for `rdf:type` triples, the filter also evaluates the object — the triple `?s rdf:type ?o` is excluded if the object `?o` is in the level's Excluded Object Types set, regardless of the fact that `rdf:type` itself is a permitted predicate. This dual evaluation ensures that OWL metamodel declarations like `?x rdf:type owl:Restriction` are excluded at Levels 1 and 2 while domain-level typing like `?x rdf:type pblr:run-01` is retained.

- **BR-6: Default level is 3 for backward compatibility**
  Omitting `--level` produces identical output to the pre-feature version. No existing workflow breaks.

- **BR-7: Unrecognized predicate handling**
  Predicates not matching any known inclusion or exclusion rule are handled as follows:
  - **Level 1 (strict):** Unrecognized predicates are **excluded**. This is a safe default — Level 1's goal is a minimal, predictable ontology. New predicates added by future py-amr2fred versions will not leak into Level 1 output unless explicitly added to the L1 permitted set.
  - **Level 2 (permissive):** Unrecognized predicates are **included**. Level 2 adds enrichments beyond the minimal set; new predicates are consistent with that goal unless they fall into an explicitly excluded namespace (owl:, framester:, fschema:, WSD).
  - **Level 3:** All predicates included (no filtering).

## Acceptance Criteria (Testable)

1. **AC-1: Default level** — When `--level` is not provided, the output RDF graph contains the same triples (same count, same content) as the output produced by the current (unmodified) text2rdf for the same input.
2. **AC-2: Level 1 triple reduction** — For a given reference input file, let N be the triple count at Level 3. Level 1 output must contain approximately 40% of N triples (±10%), i.e., between 30% and 50% of N. All remaining triples must have predicates from the Level 1 permitted set (L1-P1 through L1-P8) and, for `rdf:type` triples, objects not in the L1 Excluded Object Types set. The reference input for verification is the same input file processed at Level 3.
3. **AC-3: Level 2 triple reduction** — For a given reference input file, let N be the triple count at Level 3. Level 2 output must contain approximately 75% of N triples (±10%), i.e., between 65% and 85% of N. All remaining triples must have predicates from the Level 2 permitted set and, for `rdf:type` triples, objects not in the L2 Excluded Object Types set. The reference input for verification is the same input file processed at Level 3.
4. **AC-4: Level 3 identity** — For any input, `--level 3` output is byte-identical to output from the same input without the `--level` flag.
5. **AC-5: Level 1 excludes OWL predicates** — No triple in Level 1 output has a predicate in the `owl:` namespace.
6. **AC-6: Level 2 excludes OWL predicates** — No triple in Level 2 output has a predicate in the `owl:` namespace.
7. **AC-7: Level 2 excludes cross-ontology** — No triple in Level 2 output has a predicate `framester:subsumedUnder`, a `fschema:` (VerbAtlas) predicate, or any other cross-ontology linking predicate.
8. **AC-8: Level 3 includes all** — The union of Level 1 and Level 2 excluded triples exists in the Level 3 output.
9. **AC-9: Invalid level rejected** — Invoking `--level 0`, `--level 4`, or `--level foo` causes an argparse error and non-zero exit.
10. **AC-10: Empty graph warning** — When filtering removes all triples, a warning is printed to **stderr** and a valid empty RDF file is written.
11. **AC-11: Level 1/2 exclude WSD/Wikidata** — Level 1 and Level 2 outputs contain no triples with WordNet synset URIs or Wikidata `owl:sameAs` links.
12. **AC-12: `--no-postprocess` accepted** — The flag is accepted without error at any level combination and does not change output.
13. **AC-13: Level 1 rdf:type object filtering** — For a Level 1 output, no `rdf:type` triple has an object in the `owl:`, `framester:`, `fschema:` (VerbAtlas), `wn:`, or `wd:` namespace (e.g., `?x rdf:type owl:Restriction` is excluded).
14. **AC-14: Level 1 includes VerbNet core roles** — Triples with predicates `vn.role:Theme` and `vn.role:Agent` are present in Level 1 output (provided they exist in the Level 3 output for the same input).
15. **AC-15: Level 2 includes boxer/boxing** — Triples with predicates in the `boxer:` and `boxing:` namespaces are present in Level 2 output (provided they exist in the Level 3 output for the same input).
16. **AC-16: Level 1 excludes unrecognized predicates** — A triple whose predicate does not match any L1-P1 through L1-P8 rule is excluded from Level 1 output, even if the predicate is not in any explicitly excluded namespace.
17. **AC-17: Level 2 includes unrecognized predicates** — A triple whose predicate does not match any explicit L2 exclusion rule is included in Level 2 output, unless its predicate is in the `owl:`, `framester:`, `fschema:`, or WSD namespaces.

## Technical Notes

- **Implementation point:** The complexity filter function should be inserted as a separate step between `build_knowledge_graph()` and `serialize_output()` in `main()` — this is preferred for separation of concerns. The filter takes the merged graph and the level, and returns the filtered graph.
- **Filter mechanism:** Use `rdflib.Graph` iteration with predicate-based removal. Iterate over a snapshot of triples (`list(graph)`), evaluate each triple's predicate URI against the level's exclusion rules, and call `graph.remove(triple)` for excluded triples. Do NOT modify the graph while iterating over it directly.
- **Dual evaluation for `rdf:type`:** For `rdf:type` triples, the implementation must perform a two-step check: (1) the predicate `rdf:type` is in the Level's permitted set, AND (2) the object URI is NOT in the Level's Excluded Object Types set. Pseudocode: `if predicate == RDF.type and object_ns in excluded_object_namespaces: remove()`.
- **Level 1 is an inclusion list (positive):** Rather than defining Level 1 as "everything minus exclusions", it is safer to define it as an **inclusion list** — only triples whose predicate matches one of the L1-P1 through L1-P8 rules are kept. Unrecognized predicates are excluded by default (BR-7). This prevents accidental inclusion of new py-amr2fred predicates added in future versions.
- **Level 2 is an exclusion list (negative):** Level 2 can be implemented as "everything minus explicitly excluded predicates/namespaces". Unrecognized predicates pass through (BR-7).
- **Namespace identification:** Predicates should be matched by their full URI. Group rules by namespace prefix for maintainability. Use `rdflib.namespace` or string prefix matching on the URI.
- **`--level` CLI argument:** Use `argparse.ArgumentParser.add_argument` with `choices=[1, 2, 3]`, `type=int`, `default=3`.
- **Zombie flag `--no-postprocess`:** Retain for backward compatibility. Do NOT remove. Document that levels 1 and 2 naturally exclude WSD/Wikidata content.
- **Triple count in summary:** The summary printed by `serialize_output()` must report the count AFTER filtering, not before. The per-sentence triple counts printed during conversion can still show pre-filter counts (they come from `amr_to_rdf`).
- **Warning output:** All warnings (including the empty-graph warning from EF-3) must be written to **stderr**, not stdout. This keeps stdout clean for structured output and allows piping.

## Open Questions
- [ ] **OQ-2:** Should `rdfs:label` be included in Level 1? The analyst excluded it, but it provides human-readable labels that may be important even in a simple graph (especially if `schema:name` is included). **Current resolution: excluded at Level 1 (per BR-1), included at Level 2 (per BR-2). Revisit if user feedback indicates labels are essential at Level 1.**
- [ ] **OQ-4:** Should the filter report which triple categories were removed (e.g., "Removed 42 OWL metamodel triples, 15 cross-ontology links") or just the final count? This would require counting by category during the filter pass.
- [ ] **OQ-5:** The ~40% and ~75% thresholds are estimates. Should they be enforced as hard limits (error if actual ratio deviates by more than X%) or treated as documentation guidelines? **Current resolution: treated as documentation guidelines with ±10% tolerance in AC-2/AC-3. Revisit if real-world output consistently falls outside these ranges.**
- [ ] **OQ-7:** The namespace URIs in the Namespace Registry table must be verified against actual py-amr2fred output at implementation time. In particular, the URIs for `amrb:`, `pblr:`, `vn.role:`, `quant:`, `fschema:`, and VerbAtlas need confirmation. Implementors should run py-amr2fred on a sample input and extract the actual namespace prefixes and URIs from the serialized output to confirm these mappings.

## Resolution Log

| OQ | Resolution | Date | Applied to |
|----|-----------|------|------------|
| OQ-1 | YES — include `vn.role:Theme` and `vn.role:Agent` in Level 1 | 2026-04-08 | BR-1 (L1-P5, L1-P6), AC-14 |
| OQ-3 | EXCLUDE unknown predicates at Level 1; INCLUDE at Level 2+ | 2026-04-08 | BR-7, AC-16, AC-17 |
| OQ-6 | INCLUDE `boxer:` and `boxing:` at Level 2 | 2026-04-08 | BR-2 (L2-P5, L2-P6), AC-15 |
