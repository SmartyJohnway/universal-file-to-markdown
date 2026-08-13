# Security Policy

## Supported versions

Security fixes are currently applied to the latest release line.

| Version | Supported |
|---|---|
| 1.9.x | Yes (development line) |
| 1.8.x | Yes |
| 1.7.x | Yes |
| 1.6.x and earlier | No |

## Reporting a vulnerability

Do not disclose a suspected vulnerability in a public issue before the maintainer has had a reasonable opportunity to investigate it.

Use GitHub's private vulnerability reporting feature for this repository when available. If private reporting is unavailable, contact the maintainer through the private contact method shown on the GitHub profile and include `SECURITY: universal-file-to-markdown` in the subject.

Provide:

- affected version or commit;
- operating system and Python version;
- input format and the smallest safe reproduction available;
- impact and attack scenario;
- relevant logs with secrets and document contents removed;
- suggested mitigation, if known.

Do not attach confidential source documents. Create a synthetic reproducer whenever possible.

## Security boundaries

This project processes untrusted files with the privileges of the executing process. Users should:

- run conversions in an isolated environment for untrusted inputs;
- restrict filesystem and network access;
- enforce file-size, page-count, decompression, and execution-time limits externally;
- keep dependencies patched;
- inspect `conversion-report.json` and bundle validation results;
- never assume successful parsing means a file is safe.

The project does not execute Office macros, expand embedded OLE objects, or intentionally run active document content. Generic parsers and OCR libraries may nevertheless contain upstream vulnerabilities.

Optional Tier-2 processing is disabled by default. Its worker disables Docling
remote services and external plugins, requires manifested local model files,
and runs with timeouts, but it is not an OS sandbox. Production deployments
must still deny worker network access and enforce process/resource isolation.

## Disclosure process

The maintainer will aim to:

1. acknowledge a complete report;
2. validate severity and affected versions;
3. prepare a fix and regression test;
4. publish an advisory and patched release when appropriate;
5. credit the reporter unless anonymity is requested.

No guaranteed response or remediation timeline is promised.
