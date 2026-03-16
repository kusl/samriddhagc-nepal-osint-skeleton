## PWTT Runtime Subset

This repository vendors only the minimal runtime subset required by Nepal OSINT:

- `code/pwtt.py`

The original upstream project includes large figures, docs, notebooks, and a nested Git
repository. Those assets are intentionally excluded here to keep contributor clones and
Docker build contexts small while preserving the damage-assessment code paths that import
`pwtt_lib.code.pwtt`.
