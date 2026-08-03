# Final Dataset Notes

## Purpose

This dataset supports reproducible evaluation of metadata-based diagnosis and weighted repair planning for Fabric modpacks. It contains normalized metadata and configuration descriptions, not mod JARs or complete launcher installations.

## Source Types

- `synthetic` cases are small deterministic fixtures created for individual compatibility rules.
- `original_real` includes reduced cached examples and separately labeled complete cached Modrinth manifests. `collection_method` and provenance distinguish them; neither is redistributed as an official export.
- `modified_real` includes reduced examples and deep-copied complete-manifest controls with clearly recorded intentional injections.
- `custom_modpack` cases are deterministic offline packs used for size and controlled-error experiments.
- `custom_topology` cases are dependency-dense controlled metadata graphs, not official packs.
- `cascading_stress` cases test repairs that reveal a different issue at a later step.
- `search_stress` cases test candidate alternatives, profile sensitivity, deterministic ties, and unsatisfiable cores.
- `search_scaling_manifest.json` defines five controlled bounded supplements outside the main 158-case manifest; they measure state growth and are not official packs.
- `existing_broken` is reserved for naturally broken examples that can be independently verified.

## Error Injection

Injected and generated modifications are labeled by type and have a JSON log. They must not be described as naturally occurring failures. The original case is preserved, and injection functions operate on deep copies.

New version 2 expectations are not copied from the weighted solver under evaluation. Ground truth comes from valid controls, replayable inverse injections, or bounded exhaustive reference enumeration. Solver output is stored only as an observed evaluation result.

## Complexity

Version 2 records selected-mod count alongside required and total dependency edges, edge density, maximum required depth, branching, connected components, cycles, and candidate-version counts. Required depth is measured on the cycle-safe condensation graph. Density is reported per unique selected mod.

## Manual Review

Pending forms under `manual_review/` contain null review fields. Objective evidence packets verify available provenance, fixtures, graph/checker behavior, injection diffs, and known-repair replay. Their presence is a review queue, not evidence that review is complete. Publication-ready status requires all required judgments to be explicitly true plus a reviewer and ISO timestamp.

## Metadata Cache

Tests and demos use normalized or raw cached metadata. Live Modrinth access is optional and must be explicitly enabled. The project does not cache or redistribute mod files.

The live collector downloads only a published `.mrpack` archive long enough to extract `modrinth.index.json`; it does not retain the archive or download mod JARs. Resolution tries plausible version IDs, hashes, project-version metadata, file names, and exact download URLs, records the selected method, and isolates malformed batch members. Cases below 90% metadata coverage are recorded under `quarantine/`.

The July 2026 collection contains 20 distinct full Modrinth source manifests. Nine checker-clean manifests are included as unchanged warning-tolerant controls, each paired with one deep-copied missing-dependency injection. Eleven collected manifests are excluded from scored analysis under `quarantine/analysis-*.json` because the normalized metadata reports unresolved required targets or Minecraft-version errors. Five earlier collection attempts lack cached manifests and remain file-resolution exclusions. The generated exclusion audit classifies these conservatively; exclusion is not a claim that a public pack is broken.

## Known Limitations

Compatibility is inferred from available metadata and cannot guarantee that Minecraft will launch successfully. The current implementation focuses on Fabric and Modrinth. Basic `.mrpack` support reads its manifest but does not install, download, or regenerate a pack.

## Publication Caution

Verify Modrinth project licenses, API terms, source URLs, and redistribution requirements before publishing raw cached metadata. Report reduced, complete-manifest, custom, and intentionally modified cases separately. Complete-manifest records remain pending human publication review unless a review form proves otherwise; automated validation alone is insufficient.
