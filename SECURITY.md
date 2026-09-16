# Security Policy

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's
[private vulnerability reporting](https://github.com/16SULPHUR/webcam-bridge/security/advisories/new)
instead. Include steps to reproduce and the impact you see. You should get a
reply within a week.

## Scope notes

The desktop dashboard has no authentication by design and is meant to be
reached only from the same machine (or over USB through `adb reverse`).
Issues that need `--host 0.0.0.0` on an untrusted network are still worth
reporting, but they are treated as hardening work.
