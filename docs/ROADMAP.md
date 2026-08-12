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

## Current development line: 1.9.0

- isolated, opt-in Docling candidate worker for difficult PDF/image cases;
- allowlisted quality-gated escalation rather than a heavyweight default;
- exact offline model manifests, dual timeouts, artifact validation, and failure containment;
- native evidence is always retained; automatic arbitration is deliberately deferred.

## v1.9.1: Tier-2 qualification and v2 readiness

- pin and qualify the actual Docling/runtime/model combination;
- 10–20 public or redistributable hard documents with ground truth;
- Windows/Linux and Python 3.10–3.12 matrix where supported upstream;
- cold/warm time, memory, model/package hash, and offline execution evidence;
- candidate comparison and explicit promotion policy only if accuracy evidence supports it.

## v2.0 readiness

Schema 2.0 is not scheduled. It requires evidence that schema 1.x cannot safely represent consumer needs, plus a migration tool and consumer compatibility tests. Candidate areas include a first-class reading-order graph, typed semantic relationships, content layers, alternative extraction candidates, and richer provenance.

## Persistent non-goals

- pixel-perfect or Office round-trip reconstruction;
- allowing AI Review to mutate canonical evidence;
- making a heavyweight/model-downloading parser the default route;
- replacing deterministic OOXML parsers with model inference;
- executing Office macros or embedded active content;
- silently hiding low-confidence or unsupported structures.
