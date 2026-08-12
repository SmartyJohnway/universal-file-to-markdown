# Roadmap

This roadmap is directional and does not promise delivery dates. Canonical evidence, provenance, validation, and truthful uncertainty take priority over visually attractive reconstruction.

## Current development line: 1.7.3

Truthfulness and hardening without breaking document/table/chunk schema 1.0:

- release metadata and documentation consistency gates;
- rejected OCR candidate advisory-target closure;
- reading-order and visual-flow uncertainty reason codes;
- native runtime probe and repository validation robustness;
- focused regression expansion.

## v1.8.x: reading order and structural association

- deterministic multi-column PDF region detection and ordering;
- PPTX placeholder roles, layout zones, group hierarchy, and ambiguity handling;
- strong-evidence heading, caption, table, figure, and note associations;
- chunk context that carries validated layout/association references.

## v1.9.x: optional Tier-2 document understanding

- isolated, optional adapters for difficult PDF/image cases;
- quality-gated escalation rather than a heavyweight default engine;
- validated candidate bundles, deterministic arbitration, and failure containment;
- real hard-document qualification with pinned engine/model provenance.

## v2.0 readiness

Schema 2.0 is not scheduled. It requires evidence that schema 1.x cannot safely represent consumer needs, plus a migration tool and consumer compatibility tests. Candidate areas include a first-class reading-order graph, typed semantic relationships, content layers, alternative extraction candidates, and richer provenance.

## Persistent non-goals

- pixel-perfect or Office round-trip reconstruction;
- allowing AI Review to mutate canonical evidence;
- making a heavyweight/model-downloading parser the default route;
- replacing deterministic OOXML parsers with model inference;
- executing Office macros or embedded active content;
- silently hiding low-confidence or unsupported structures.
