# Final Repository Hardening Implementation Report

1. **Starting verification:** The pass began from 334 passing tests, one opt-in live test skipped, and one stress test deselected. The 25-case, 64-case v1, and 158-case evaluations all passed before edits.
2. **Starting corpus:** The main manifest contained 158 cases in 89 source families. Source counts were synthetic 19, original real 11, modified real 13, custom modpack 39, custom topology 48, cascading stress 12, and search stress 16.
3. **Starting review labels:** Manifest labels were legacy retained 58, validated 64, validated pending manual review 30, and validated reduced metadata 6. These labels are distinct from the new human-review statuses.
4. **Files added:** Major additions are `manual_review.py`, `search_scaling.py`, `exclusion_review.py`, `reproducibility.py`, four corresponding root runners, five scaling fixtures and their manifest, qualitative tool-comparison files, and focused tests.
5. **Files changed:** The Modrinth collector, final report models/runner/paper/summary, collector/evaluation/paper tests, five current-state documentation files, manual-review forms, and generated final artifacts were updated. The 158-case main manifest and v1 manifest were not edited.
6. **Manual-review workflow:** Objective evidence now checks provenance, source/cache presence, fixture loading, graph/checker behavior, injection diffs, and known-repair replay. Subjective fields remain human-only.
7. **Review enforcement:** `human_reviewed` and `publication_ready` require every judgment, an ISO timestamp, and a reviewer. Publication-ready additionally requires every judgment to be true.
8. **Review packets:** Sixty-two automated evidence packets and 62 human forms were generated across complete manifests and variants, cascades, no-solution cases, and stratified dense controls.
9. **Review status:** Fifty-six packets are automated-evidence-ready, six require objective evidence correction, all 62 still require human review, and zero are publication-ready or rejected.
10. **Search supplement:** Five deterministic cases were added under `data/final_dataset/search_scaling/`, outside the main corpus. Ground truth uses replayable inverse repairs, not weighted-solver labels.
11. **Scaling result 1:** Moderate solved correctly at 32 states; median/min/max runtime was 12.638/12.379/12.710 ms.
12. **Scaling result 2:** Intermediate solved correctly at 128 states; runtime was 75.544/69.365/75.906 ms.
13. **Scaling result 3:** Deep interaction solved correctly at 212 states; runtime was 122.667/117.255/133.981 ms.
14. **Scaling result 4:** High bounded stress correctly reached its 500-state limit while retaining a replayable valid repair; runtime was 314.540/302.172/316.704 ms.
15. **Scaling result 5:** Extreme bounded stress correctly reached its 750-state limit while retaining a replayable valid repair; runtime was 977.145/967.360/1000.541 ms.
16. **Scaling interpretation:** All five outcomes and target ranges passed. This is controlled state-growth evidence, not complete-pack or launcher scalability evidence.
17. **Collector fallbacks:** Resolution now supports plausible explicit IDs, global lookups, SHA-1/SHA-512 lookup, project-version matching by version number/file/hash, exact download-URL matching, and unresolved records.
18. **Collector robustness:** Version-like strings such as `0.1.3` and `1.1.1+1.17` are not assumed to be global IDs. Individual batch failures no longer discard successful members, fallback resolutions are cached/recorded, and no mod JAR is fetched.
19. **Failed collection replay:** Zero of the five historical failures could be recovered offline because their source manifests were not cached. All five remain unresolved; no metadata-coverage increase could be established without a new opt-in live collection.
20. **Exclusion review:** Sixteen records were audited: five file-resolution failures, one incomplete collection, six normalization limitations, one version-declaration mismatch, and three ambiguous manual-review cases.
21. **Exclusion outcome:** Zero cases were recovered and all 16 remain quarantined. A checker finding is explicitly not treated as proof that a public pack is broken or cannot launch.
22. **Documentation:** README, AGENTS, architecture, dataset notes, and changelog now distinguish reduced, complete-manifest, modified real-derived, dense topology, cascading, scored search, supplementary scaling, and quarantined evidence.
23. **Solver table:** The main table is reduced to eight columns: method, repairs, success, full preservation, mean preservation, mean removals, median runtime, and failures.
24. **Solver denominator:** Mean preservation is among successful repairs; full-preservation counts use all 104 expected-repair cases. Raw cross-profile costs are omitted.
25. **Complexity table:** Every row reports total cases, repairable cases, successful repairs, repair success, median runtime, median states, and mean repair actions. LaTeX uses `tabularx`.
26. **Explanation claims:** Automated structured completeness, dependency-chain correctness, and cascading-step correctness are reported separately from human understandability. Human understandability currently has 0 reviewed records out of 62 queued.
27. **Evidence scope:** Complete manifests demonstrate real Modrinth metadata ingestion; controlled modified, topology, cascading, and search inputs provide algorithmic comparisons. No launch-success claim is made.
28. **External tools:** Markdown and LaTeX provide a qualitative comparison with Minecraft Launcher, Modrinth App, CurseForge App, Prism Launcher, packwiz, and ezMMCC. It makes no performance or launcher-superiority claim and retains citation TODOs.
29. **Final baseline:** The one-pass baseline repaired 91/104 cases (87.50%), with 94.93% mean preservation among successes, 71/104 full preservation, 0.220 mean removals, and 1.628 ms median runtime.
30. **Final weighted default:** It repaired 104/104, with 97.46% mean preservation, 88/104 full preservation, 0.154 mean removals, and 3.601 ms median runtime.
31. **Final preservation profile:** It repaired 104/104, with 98.42% mean preservation, 92/104 full preservation, 0.115 mean removals, and 3.683 ms median runtime.
32. **Cascading result:** Weighted default repaired all 11/11 repairable cascading cases; the baseline repaired 3/11.
33. **No-solution and oracle results:** Weighted profiles made 13/13 correct no-solution decisions and agreed with all 12/12 solver-comparable optimal oracle plans among 17 exhaustively verified cases.
34. **Clustered intervals:** Family-clustered 95% repair-success intervals are 81.7%-92.9% for baseline and 100%-100% for both weighted profiles. Full-preservation intervals are 58.9%-77.9%, 78.0%-92.2%, and 82.5%-95.4%.
35. **Timing protocol:** Every final operation used one unmeasured warm-up and three measured `time.perf_counter()` repetitions. Median is primary; raw samples, minimum, and maximum are retained. GUI/import time is excluded.
36. **Main-corpus search:** The maximum weighted state count in the scored corpus remained 36; the separate supplement is the evidence for 32-750-state growth.
37. **Final tests:** `uv run pytest` completed with 353 passed, one live test skipped, and one stress test deselected. `uv run pytest -m stress` passed 1/1.
38. **Legacy regressions:** The strict evaluation passed 25/25 and immutable `manifest_v1.json` passed 64/64 with no weighted failures.
39. **Expanded regression:** The final run validated 158/158 cases, emitted 474 system-case results, and had zero weighted failures.
40. **GUI/demo:** `final_gui.py --smoke-test` and `demo_final_system_readable.py` both completed successfully offline.
41. **Reproducibility:** `reproducibility.json`, `REPRODUCIBILITY.md`, and `checksums.sha256` record environment, commands, profiles, limits, dataset/result hashes, and the no-JAR policy. Main manifest SHA-256 is `a02a919357a73f0f35904874cb8cd61617c2d4a3dfbf539036f29db0bf52abdc`.
42. **Remaining human work:** Complete the 62 queued judgments, resolve the six evidence warnings, verify external-tool citations/access dates, and commit the final state before publication. Git commit and clean-tree status are unavailable in this workspace and are recorded as unknown.
43. **Remaining limitations:** Results cover Fabric/Modrinth metadata, not runtime launch behavior. Public metadata can be incomplete or semantically ambiguous; controlled cases are not official packs; no external quantitative benchmark, mod installation, JAR parsing, or launcher replacement is claimed.

## Commands To Run Next

```powershell
uv run python run_manual_review.py --case-id CASE_ID
uv run python run_manual_review.py --summary
uv run python run_reproducibility_freeze.py --test-result "..." --legacy-result "..." --expanded-result "..."
```

After committing the final files, rerun the reproducibility freeze so it can record a real commit hash and clean working tree. Live collection remains optional and should only be rerun intentionally.
