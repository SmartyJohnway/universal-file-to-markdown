# Tier-2 qualification protocol

`scripts/qualify_tier2.py` turns optional Tier-2 claims into reproducible
evidence. It supports two deliberately different modes:

- `smoke`: one or more documents may prove that a pinned runtime/model can
  execute the adapter contract on one environment. A passed smoke is never a
  production qualification.
- `qualification`: requires at least ten hash-pinned public documents, two
  runs per document, complete source/license provenance, and coverage of every
  hard-document tag defined by the script.

Create a local corpus manifest conforming to
`schemas/tier2-qualification-corpus.schema.json`. Keep downloaded/public test
documents and reports outside release packages unless redistribution rights
are explicit.

```bash
python scripts/qualify_tier2.py \
  --corpus /qualification/corpus.json \
  --model-manifest /models/tier2-model-manifest.json \
  --output /qualification/results \
  --mode smoke --runs 2
```

Each case pins the input SHA-256, provenance, tags, allowed result states,
minimum candidate text/table evidence, optional required Markdown fragments,
and an optional runtime ceiling. The runner validates the native bundle,
candidate sidecar, canonical fingerprint, expectations, and rerun artifact
hashes.

Even a fully passed corpus report keeps `production_qualified=false` until
separate multi-platform, peak-memory/resource-isolation, and Hermes consumer
evidence exists. This prevents a Windows smoke or a synthetic corpus from
being promoted into a broader support claim.
