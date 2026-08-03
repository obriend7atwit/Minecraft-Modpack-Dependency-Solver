# Qualitative External-Tool Comparison

This matrix compares documented product roles and capabilities. It is not a performance benchmark, and `Not documented` means that the capability was not established from the sources reviewed for this project rather than that it cannot exist.

| Tool | Primary purpose | Direct dependency assistance | Diagnose an existing invalid pack | Compare complete multi-step repairs | Weighted user preferences | Explain rejected alternatives |
| --- | --- | --- | --- | --- | --- | --- |
| Official Minecraft Launcher | Game installation and launch | Not documented | Not documented | Not documented | Not documented | Not documented |
| Modrinth App | Modpack installation and instance management | Partial | Partial | Not documented | Not documented | Not documented |
| CurseForge App | Profile and modpack management | Partial | Partial | Not documented | Not documented | Not documented |
| Prism Launcher | Multi-source instance management | Manual | Partial | Not documented | Not documented | Not documented |
| packwiz | Modpack authoring and dependency assistance | Yes | Partial | Not documented | Not documented | Not documented |
| ezMMCC | Narrow duplicate-class conflict detection | Not applicable | Partial | Not documented | Not documented | Not documented |
| Proposed weighted solver | Metadata diagnosis and weighted repair planning | Yes | Yes, at metadata level | Yes | Yes | Yes |

Existing launchers provide broader installation and instance-management functionality, while some tools provide direct dependency assistance or preventive filtering. The reviewed public descriptions do not document the same combination of complete multi-step repair search, configurable disruption weights, preservation-oriented optimization, cascading-repair planning, and explanation of alternatives. The proposed solver targets that narrower repair-planning gap; it is not intended to replace a launcher, and no superiority or external performance claim is made without a shared benchmark.

## Source Notes

- TODO(author): Verify and cite the official Minecraft Launcher feature documentation and record the access date.
- TODO(author): Verify and cite the Modrinth App feature documentation and record the access date.
- TODO(author): Verify and cite the CurseForge App feature documentation and record the access date.
- TODO(author): Verify and cite the Prism Launcher documentation and record the access date.
- TODO(author): Verify and cite the packwiz documentation and record the access date.
- TODO(author): Verify and cite the ezMMCC repository or documentation and record the access date.
- Proposed-solver capabilities are established by this repository's implementation and offline tests.
