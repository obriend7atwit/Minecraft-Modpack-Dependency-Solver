# Excluded Complete-Manifest Review

This offline review classifies collection and normalization limitations. A checker finding is **not** treated as proof that a public modpack is broken or unable to launch.

| Measure | Count |
| --- | ---: |
| Total exclusions reviewed | 16 |
| Incomplete resolution or collection | 6 |
| Likely metadata-semantics or normalization cases | 7 |
| Ambiguous cases | 3 |
| Recovered after recheck | 0 |
| Still quarantined | 16 |

## Cause Counts

| Conservative classification | Count |
| --- | ---: |
| `file_resolution_failure` | 5 |
| `incomplete_metadata_collection` | 1 |
| `normalization_limitation` | 6 |
| `requires_manual_review` | 3 |
| `version_declaration_mismatch` | 1 |

## Pack Review

| Source pack | Coverage | Unresolved files | Classification | Confidence | Manual review |
| --- | ---: | ---: | --- | --- | --- |
| aged | 0.9952830188679245 | 1 | `incomplete_metadata_collection` | high | yes |
| ardacraft | unknown | unknown | `file_resolution_failure` | high | yes |
| better-mc-fabric-bmc2 | unknown | unknown | `file_resolution_failure` | high | yes |
| brasil-cobblemon-mobile | 1.0 | 0 | `normalization_limitation` | medium | yes |
| cobblemon-fabric | 1.0 | 0 | `normalization_limitation` | medium | yes |
| cobbleverse | 1.0 | 0 | `requires_manual_review` | low | yes |
| distant-horizons-iris-shaders | 1.0 | 0 | `normalization_limitation` | medium | yes |
| fps | 1.0 | 0 | `normalization_limitation` | medium | yes |
| fresh-smooth | 1.0 | 0 | `requires_manual_review` | low | yes |
| landscapes-reimagined-genesis | unknown | unknown | `file_resolution_failure` | high | yes |
| optifabric-modpack | 1.0 | 0 | `normalization_limitation` | medium | yes |
| pokemon-elysium | unknown | unknown | `file_resolution_failure` | high | yes |
| prominence-2-fabric | unknown | unknown | `file_resolution_failure` | high | yes |
| skyblock-enhanced | 1.0 | 0 | `normalization_limitation` | medium | yes |
| sodiumplus | 1.0 | 0 | `requires_manual_review` | low | yes |
| vanilla-perfected | 1.0 | 0 | `version_declaration_mismatch` | medium | yes |

All recovered cases, if any, remain outside the scored corpus until metadata completeness, independent ground truth, automated validation, and human review are established. These findings belong in limitations and future-work discussion.
