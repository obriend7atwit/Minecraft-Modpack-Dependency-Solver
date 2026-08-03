# Final Evaluation Summary

## Dataset Overview

The final manifest contains 158 offline-reproducible cases. Automated validation passed 158 of 158 checked cases.

The cases represent 89 distinct source families. Required-edge counts range from 0 to 475, and maximum dependency depth reaches 16.

Source counts: cascading_stress=12, custom_modpack=39, custom_topology=48, modified_real=13, original_real=11, search_stress=16, synthetic=19.

Size counts: huge=20, large=22, medium=28, small=88.

## Input Types

The final application accepts existing project JSON, built-in/final-dataset cases, basic `.mrpack` manifests, Modrinth URLs backed by normalized cache entries, and project ID/slug lists.

## Real-World Modrinth Coverage

The scored corpus includes 9 complete cached Modrinth manifest controls and 9 paired inverse-injected variants, plus 2 reduced real-data controls and 4 reduced variants. Complete-manifest means the normalized metadata covers the pack's full Modrinth file list; it does not mean the project redistributes an official pack export. All complete-manifest cases remain pending manual review.

## Error Injection Method

Modified cases are labeled and logged. Modification counts are add_conflicting_mod=4, candidate_choice=8, cascading_repair=11, change_loader=1, change_minecraft_version=1, duplicate_mod_version=4, manual=11, multi_error=4, none=50, remove_required_dependency=31, replace_with_incompatible_version=24, tie_breaking=4, unsatisfiable=5. Injection operates on copied cases, records the change, and is rechecked through the normal graph/checker/solver pipeline.

## Baselines

One-pass baseline: 91/104 expected repairs succeeded (87.50%); average successful-repair preservation was 94.93%; median runtime was 1.628 ms.

One-pass baseline: 71/104 expected-repair cases were repaired with full preservation (68.27%). Preserved original mods across the same expected-repair denominator were 94.04%; failed repairs contribute zero to this strict measure.

The baseline applies checker suggestions once in order. It does not search, backtrack, or compare weighted alternatives.

## Weighted Solver Results

Default weighted profile: 104/104 expected repairs succeeded (100.00%); average successful-repair preservation was 97.46%; median runtime was 3.601 ms.

Default weighted profile: 88/104 expected-repair cases were repaired with full preservation (84.62%). Preserved original mods across the same expected-repair denominator were 99.76%; failed repairs contribute zero to this strict measure.

Preservation-focused profile: 104/104 expected repairs succeeded (100.00%); average successful-repair preservation was 98.42%; median runtime was 3.683 ms.

Preservation-focused profile: 92/104 expected-repair cases were repaired with full preservation (88.46%). Preserved original mods across the same expected-repair denominator were 99.82%; failed repairs contribute zero to this strict measure.

Raw costs should only be interpreted within a profile because each profile uses a different weight scale.

Cascading and reference results: 11/11 repairable cascading cases succeeded; 12 optimal-plan agreements among solver-comparable oracle cases from 17 exhaustively verified cases; 13/13 no-solution outcomes were correct.

## Results by Pack Size

Small, medium, large, and huge results are exported in the case-category table and pack-size charts. Large results include controlled metadata and cached complete-manifest cases; huge results are controlled generated metadata stress cases.

## Results by Source Type

Source types remain separate in the exported tables and charts so synthetic/custom results are not presented as real-pack evidence.

## Large and Huge Modpack Results

The manifest includes 22 large and 20 huge cases. They test graph/checker/solver scaling but do not establish full ecosystem coverage.

## Explanation Review

Structured weighted-explanation completeness was 100.00% for the default profile and 100.00% for the preservation profile. This is an automated field-completeness check, not a human-readability score.

Default-profile explanation checks: dependency-chain accuracy=100.00%; cascading-step accuracy=100.00%; global-plan-reason accuracy=100.00%.

Human understandability review: 0/0 explicitly reviewed records were marked understandable; 62 queued records have no human judgment.

## Review Status

Automated validation: 158/158 scored cases passed. Human review: 0/62 queued records are explicitly human-reviewed. Publication-ready review: 0/62 records meet the strict publication-ready status. Complete-manifest cases remain pending human publication review unless their records explicitly prove otherwise.

## Failure Analysis

No weighted case-results were assigned a failure category.

## Key Findings

On this dataset, the default weighted solver changed repair success by +12.50 percentage points relative to the one-pass baseline. The preservation profile changed average preservation by +0.96 percentage points relative to the default profile. These observations apply only to the evaluated corpus.

## Limitations

Results describe metadata compatibility, not guaranteed launch-time behavior. Support is Fabric/Modrinth-focused. The `.mrpack` reader does not install or regenerate packs, and live API data may change after this offline snapshot.

## Reproducibility Notes

Normal tests, demos, validation, and final evaluation run offline. New case expectations use controls, inverse injections, or reference enumeration rather than weighted-solver output. Live collection is optional and must be explicitly enabled.

## Generated Files

The run generated 49 JSON, CSV, Markdown, LaTeX, and PNG artifacts under `results\final`.
