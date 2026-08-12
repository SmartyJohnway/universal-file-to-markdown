# Security Model

## Trust assumptions

The converter may receive malformed or hostile files. It runs with the privileges, filesystem access, network access, memory, and CPU limits of the invoking process.

## Defensive design

The project currently:

- distinguishes encrypted, corrupt, valid, and unknown Office-container states;
- avoids executing Office macros and embedded OLE objects;
- sanitizes extracted EML attachment names;
- uses deterministic local parsers and offline OCR by default;
- clears known stale bundle artifacts before a rerun;
- validates canonical schemas and cross-file references;
- reports unsupported or uncertain content explicitly.
- keeps optional Tier-2 output candidate-only, runs it in a child process with
  offline flags and timeouts, disables Docling remote services/plugins, and
  verifies local model plus candidate artifact hashes.

## External controls still required

Deployments handling untrusted files should add:

- process or container isolation;
- read-only inputs and dedicated output directories;
- memory, CPU, wall-time, file-size, page-count, and archive-expansion limits;
- network denial unless explicitly required;
- dependency vulnerability monitoring;
- malware scanning where appropriate;
- retention and deletion policies for source files and extracted assets.

## Non-goals

The project is not:

- an antivirus product;
- a content-disarm-and-reconstruction system;
- a sandbox by itself;
- a guarantee that offline environment flags equal operating-system network isolation;
- a guarantee that successfully parsed content is trustworthy;
- a substitute for data-classification or privacy controls.

See `SECURITY.md` for vulnerability reporting.
