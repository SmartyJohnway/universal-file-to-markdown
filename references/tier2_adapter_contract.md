# Optional Tier-2 adapter contract

Skill version `1.9.0` introduces a candidate-only adapter framework for
difficult PDF and raster-image cases. It does not make Docling a core
dependency, does not route Office files through a model, and does not replace
native canonical evidence automatically.

## Safety and trust boundary

The native router always runs first. A Tier-2 worker may write only under
`tier2/candidate/`. Before and after the worker, the adapter fingerprints
`document.json`, `chunks.jsonl`, and canonical table JSON. Any change is a
fatal containment failure.

The built-in worker:

- runs in a child process with an outer wall-time limit;
- sets Hugging Face and Transformers offline environment flags;
- configures Docling with `enable_remote_services=False`;
- configures `allow_external_plugins=False`;
- requires a local `artifacts_path` backed by an exact file/hash manifest;
- applies an independent Docling document timeout;
- emits Docling JSON and Markdown as candidates, never as canonical truth.

Environment flags and Docling options reduce unintended network use; they are
not an operating-system network sandbox. Deployments processing untrusted or
confidential files must still deny network access and constrain CPU, memory,
filesystem, page count, and process privileges externally.

## Model manifest

The model directory must contain `tier2-model-manifest.json`. Create it only
after pre-downloading and pinning the exact files in the separate Tier-2
environment:

```bash
python scripts/tier2_model_manifest.py create /models/docling \
  --model-id docling-standard-pipeline \
  --model-version YOUR-QUALIFIED-MODEL-REVISION
python scripts/tier2_model_manifest.py verify \
  /models/docling/tier2-model-manifest.json
```

Every regular file except the manifest itself is included with relative path,
size, and SHA-256. Missing, additional, changed, duplicate, escaping, or
symlinked artifacts fail closed. The manifest describes local artifacts; it
does not by itself prove model quality.

Docling is intentionally not listed in core `requirements.txt`. Install and
qualify it in a separate persistent environment, following its upstream
installation and offline-model guidance. Record the exact Docling and model
versions in qualification evidence before production use.

## Invocation

Default behavior remains completely unchanged:

```bash
python scripts/router.py source.pdf --output bundle
```

Explicitly opt into quality-gated candidate generation:

```bash
python scripts/router.py source.pdf --output bundle \
  --tier2 auto \
  --tier2-model-manifest /models/docling/tier2-model-manifest.json
```

`auto` launches only for PDF/image warnings in the allowlist, including
unverified table structure and reading-order/table-association uncertainty.
`force` bypasses the quality signal for PDF/image qualification work, but does
not bypass format, manifest, security, validation, or containment gates.

Optional limits:

```text
--tier2-timeout-seconds           outer subprocess wall time (default 120)
--tier2-document-timeout-seconds  Docling document timeout (default 90)
```

## Serialized output

When `--tier2` is enabled, `tier2/index.json` records one of:

- `not_triggered`
- `not_eligible`
- `unavailable`
- `timed_out`
- `failed`
- `candidate_available`

Candidate success also writes:

```text
tier2/request.json
tier2/candidate/worker-result.json
tier2/candidate/docling-document.json
tier2/candidate/document.md
```

The index records trigger/reason codes, source and model-manifest hashes,
adapter version, duration, before/after native fingerprints, and the fixed
selection state `native_retained_pending_manual_review`. Standalone bundle
validation checks index schema, source identity, native fingerprints, worker
schema, security flags, and every candidate artifact hash.

## Deliberate non-claims

v1.9.0 proves adapter isolation and contract behavior with synthetic workers.
It does not claim:

- that Docling is installed in the core runtime;
- a qualified Docling/model version;
- better accuracy on a representative hard-document corpus;
- automatic candidate arbitration;
- cross-platform Tier-2 performance or reproducible model packages.

Those are v1.9.1 evidence gates. Until they pass, a human or downstream agent
may compare the candidate with native evidence, but must not silently promote
it to canonical truth.
