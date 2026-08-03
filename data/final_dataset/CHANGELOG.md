# Final Dataset Changelog

## Repository hardening pass (dataset remains 2.0.0)

- Preserved the 158-case main manifest and 64-case version 1 regression manifest unchanged.
- Added traceable automated evidence packets and strict publication-ready human-review validation.
- Added a separate five-case controlled search-scaling manifest with independent ground truth.
- Added conservative Modrinth version, hash, project-version, filename, and URL resolution fallbacks with method records.
- Classified all cached excluded complete-manifest and failed collection records without labeling public packs as broken.
- Added compact solver and complexity paper tables with explicit denominators and separate confidence intervals.
- Separated automated explanation completeness from human understandability review.
- Added evidence-scope and qualitative external-tool comparison artifacts without external performance claims.
- Added raw timing samples and reproducibility-freeze support; no mod JARs are retained.

## 2.0.0

- Retained all 64 version 1 cases and preserved their original manifest as `manifest_v1.json`.
- Added 48 dependency-dense topology cases across small, medium, large, and huge sizes.
- Added 12 dedicated cascading-repair cases with replayable issue traces.
- Added 16 candidate-choice, profile-sensitive, tie-breaking, and unsatisfiable search cases.
- Added source-family, provenance, metadata-coverage, graph-complexity, ground-truth, review, and repair-trace fields.
- Replaced solver-generated labels for new cases with original-control, inverse-injection, or exhaustive-reference ground truth.
- Added a manual-review queue without claiming that pending records have been reviewed.
- Added optional full Modrinth `.mrpack` collection and quarantine infrastructure.
- Collected 20 distinct complete Modrinth source manifests without retaining archives or JARs.
- Added 9 checker-clean complete-manifest controls and 9 inverse-validated missing-dependency variants to the scored corpus.
- Recorded 11 metadata-ambiguous collected manifests as analysis exclusions rather than assigning unsupported ground truth.
- Expanded the scored version 2 corpus to 158 cases across 89 source families.
- No naturally broken public case currently meets the documented reproduction and review criteria.

## 1.0.0

- Original 64-case corpus combining deterministic synthetic cases, reduced cached-real references, modified reduced-real cases, and shallow custom scale cases.
- Retained unchanged for regression evaluation.
