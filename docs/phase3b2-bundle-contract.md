# Phase 3B.2 authoritative candidate bundle

## Purpose and limits

Phase 3B.2 builds an offline, inactive production candidate from the pinned Phase 3B.1 selections and the exact historical slice ending 2026-10-01. It does not activate models, write forecast or `ModelArtifact` rows, create Azure resources, or deploy anything. Activation evaluation belongs to Phase 3B.3.

## Canonical inventory

The universe comes only from `get_all_configured_symbols()` in `backend/app/domain/company_universe.py`: ALI, APX, BPI, GLO, ICT, JFC, MBT, MEG, MER, NIKL, PGOLD, SCC, SECB, SHLPH, and SMPH. Each company has one LIR, one ARIMA, and one LSTM artifact: 45 binaries total.

Every company must have exactly 1,649 ordered, unique OHLCV rows from 2020-01-02 through 2026-10-01. Preflight compares every row and OHLCV value to the pinned official source. Rows after the cutoff are excluded and reported; they are not changed.

## Output and atomicity

The builder writes to `~/pse-pulse-production-artifacts/2026.10.01-authoritative-v1/`, outside the repository. It rejects an existing final directory. Training and verification happen in a sibling staging directory; only a complete, verified staging directory is atomically renamed to the final name. Any training or verification failure removes staging and leaves no final candidate.

The final directory contains `manifest.json` and, for each canonical symbol, `lag_regression.joblib` plus metadata, `arima.joblib` plus metadata, and `lstm.pt` plus metadata. That is 91 files: 45 binaries, 45 metadata files, and one manifest. The acceptance inference evidence is stored beside the bundle as `bundle_validation.json`, not inside the immutable bundle.

## Selection and artifact rules

All model version fields equal `2026.10.01-authoritative-v1`. LIR uses the selected per-company alpha with Phase 3A's production-history PACF and causal feature semantics. ARIMA uses the selected order and trend and must confirm convergence. LSTM uses the selected architecture/training settings, CPU execution, and its fresh two-stage production epoch selection; the formal epoch count remains evidence only.

Each joblib metadata document binds company, family, implementation/schema, history boundary, authoritative regime, and exact selection provenance. The loader checks these fields and company-specific parameters before delegating to the existing SHA-before-joblib loader. LSTM continues to use the state-dict safe loader with CPU mapping and `weights_only=True`.

## Manifest and verification

The manifest has schema `pse-pulse.production-bundle`, version 1. Entries are ordered by symbol then LAG_REGRESSION, ARIMA, LSTM. It includes pinned methodology/data provenance, selection CSV SHA and Git blob, formal run identity, build environment, artifact/metadata hashes and sizes, and model-specific selection evidence. JSON is UTF-8, sorted by key, indented by two spaces, rejects NaN, and ends with one newline.

The standalone `scripts/phase3b2_verify_bundle.py` does no training. It validates inventory, paths, hashes, metadata, catalog binding, history limits, and safe reload of all 45 artifacts. A verifier failure means the bundle is not accepted.

## Acceptance boundary

The builder must safely reload all 45 files from disk and produce a finite positive one-step forecast for each model using the last included history row as origin. It records formal and fresh production LSTM epochs separately. Database forecast and model-artifact row counts must have zero delta. No commit or push is part of Phase 3B.2 execution.
