from __future__ import annotations

import os

import pytest

from modpack_solver.metadata.modrinth import (
    check_modrinth_fabric_api_access,
    fetch_project_summary,
)


pytestmark = [
    pytest.mark.live_api,
    pytest.mark.skipif(
        os.environ.get("RUN_MODRINTH_LIVE_TESTS") != "1",
        reason="Set RUN_MODRINTH_LIVE_TESTS=1 to run live Modrinth API tests.",
    ),
]


def test_modrinth_fabric_api_access() -> None:
    mod_summary = check_modrinth_fabric_api_access()
    modpack_summary = fetch_project_summary("fabulously-optimized")

    print(
        "Connected to Modrinth successfully.\n"
        f"Mod example: title={mod_summary['title']}, slug={mod_summary['slug']}, "
        f"type={mod_summary['project_type']}, project_id={mod_summary['project_id']}\n"
        f"Modpack example: title={modpack_summary['title']}, slug={modpack_summary['slug']}, "
        f"type={modpack_summary['project_type']}, project_id={modpack_summary['project_id']}"
    )

    assert mod_summary["slug"] == "fabric-api"
    assert mod_summary["title"] == "Fabric API"
    assert mod_summary["project_type"] == "mod"
    assert mod_summary["project_id"]

    assert modpack_summary["slug"] == "fabulously-optimized"
    assert modpack_summary["project_type"] == "modpack"
    assert modpack_summary["project_id"]
