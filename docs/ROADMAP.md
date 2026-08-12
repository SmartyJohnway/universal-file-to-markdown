# Roadmap

This roadmap is directional and does not promise delivery dates. Canonical evidence, provenance, validation, and truthful uncertainty take priority over visually attractive reconstruction.

## Implemented foundation: 1.8.0

Reading order and structural association without breaking document/table/chunk schema 1.0:

- line-aware deterministic multi-column PDF regions and table insertion;
- PPTX placeholder roles, layout zones, column flows, and group fallback;
- additive canonical layout hints;
- strong-evidence caption/table/figure and speaker-note/slide relationships;
- validation of reading-order and association references.

## Implemented foundation: 1.8.1

- chunk metadata carries validated layout/association references;
- related/ancestor element IDs are emitted without copying target content;
- source-first context budget accounting retains the 2,000-character limit;
- a machine-readable multi-bundle scorecard supports RAG/agent qualification.

## Implemented foundation: 1.9.0

- isolated, opt-in Docling candidate worker for difficult PDF/image cases;
- allowlisted quality-gated escalation rather than a heavyweight default;
- exact offline model manifests, dual timeouts, artifact validation, and failure containment;
- native evidence is always retained; automatic arbitration is deliberately deferred.

## Current development line: 1.9.1 qualification readiness

- locale-independent UTF-8 subprocess I/O and an official ONNX layout runtime avoid Windows CP950 and runtime compiler failures;
- explicit Tier-2 page-count and input-file-size limits complement the existing timeouts;
- hash-pinned corpus and report schemas plus a repeatable smoke/qualification runner;
- fail-closed gates require at least ten provenance-complete hard documents and two deterministic runs;
- every report retains `production_qualified=false` until Windows/Linux, Python 3.10–3.12, peak-resource, and Hermes consumer evidence is aggregated.

Still required before an engine/model support claim: 10–20 public or
redistributable hard documents with ground truth, the multi-platform matrix,
cold/warm memory/runtime evidence, and an explicit promotion policy supported
by accuracy results.

## v2.0 readiness

Schema 2.0 is not scheduled. It requires evidence that schema 1.x cannot safely represent consumer needs, plus a migration tool and consumer compatibility tests. Candidate areas include a first-class reading-order graph, typed semantic relationships, content layers, alternative extraction candidates, and richer provenance.

## Persistent non-goals

- pixel-perfect or Office round-trip reconstruction;
- allowing AI Review to mutate canonical evidence;
- making a heavyweight/model-downloading parser the default route;
- replacing deterministic OOXML parsers with model inference;
- executing Office macros or embedded active content;
- silently hiding low-confidence or unsupported structures.
