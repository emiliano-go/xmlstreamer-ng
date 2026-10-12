# Security Policy

xmlstreamer exists to parse untrusted XML from remote sources, so
security reports are taken seriously.

## Reporting a vulnerability

- Do NOT open a public issue for a vulnerability or a working exploit.
- Preferred channel: GitHub's private vulnerability reporting - the
  "Report a vulnerability" button on this repository's Security tab.
- If that button is not available, use the maintainer email published
  in `pyproject.toml`: carlosandresplanchonprestes@gmail.com.

A useful report includes: the affected version, a minimal reproduction
(a small synthetic feed snippet rather than a URL, which can carry
credentials), the estimated impact, and any mitigation you know.

Reports are assessed case by case. There is no formal SLA; you will
get an acknowledgment, and credit when a fix ships if you want it.

## Scope notes

- The per-item parser rejects entity declarations and external entity
  references (billion-laughs and XXE seeds are discarded and logged).
  Bypasses of that protection are especially welcome reports.
- Hostile or malformed input is this library's expected territory: a
  crash, hang or unbounded memory growth caused by crafted input is
  security-relevant here, not "just a bug".
