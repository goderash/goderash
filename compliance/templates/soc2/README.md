# SOC 2 evidence templates

This directory holds regulation-specific prose, control maps, and exhibit
templates that get embedded in generated packs during FDE onboarding.

Minimum starter set (populate during design-partner engagements):

- `trust_services_criteria.md` — narrative mapping Goderash-observable signals
  to TSC CC1 through CC9.
- `control_narratives/` — per-control one-page write-ups referencing ledger
  event types.
- `exhibits/` — sample reports an auditor expects (access reviews, incident
  log, change management log) rendered from ledger data.

The generator in `python/core/src/goderash_core/packs/soc2.py` reads these
templates and merges them with live ledger data to produce the audit bundle.
