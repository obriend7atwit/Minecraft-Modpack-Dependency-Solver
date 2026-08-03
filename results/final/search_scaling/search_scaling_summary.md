# Search Scaling Supplement

This supplementary controlled experiment measures search-state growth. It is separate from the main corpus and does not represent complete official modpacks.

One unmeasured warm-up preceded 3 measured solver-only repetitions. Runtime uses `time.perf_counter()` and reports the median with retained minima and maxima.

| Case | Observed status | States | Target | Median ms | Correct |
| --- | --- | ---: | ---: | ---: | --- |
| search-scale-01-moderate | solution_found | 32 | 25-60 | 12.638 | True |
| search-scale-02-intermediate | solution_found | 128 | 70-150 | 75.544 | True |
| search-scale-03-deep-interaction | solution_found | 212 | 175-350 | 122.667 | True |
| search-scale-04-high-bounded | limit_reached | 500 | 350-650 | 314.540 | True |
| search-scale-05-extreme-bounded | limit_reached | 750 | 650-850 | 977.145 | True |

Limit-reached cases retain independently replayed valid repairs; reaching a configured bound is not evidence that no valid repair exists. These controlled cases do not establish real-world launcher scalability.
