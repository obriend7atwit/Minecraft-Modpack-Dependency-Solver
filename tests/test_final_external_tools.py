from pathlib import Path


def test_external_tool_comparison_is_qualitative_and_complete():
    docs = Path("docs/external_tools_comparison.md").read_text(encoding="utf-8")
    paper = Path("results/final/paper/external_tools_comparison.md").read_text(
        encoding="utf-8"
    )
    latex = Path("results/final/paper/external_tools_comparison.tex").read_text(
        encoding="utf-8"
    )
    for tool in (
        "Minecraft Launcher",
        "Modrinth App",
        "CurseForge App",
        "Prism Launcher",
        "packwiz",
        "ezMMCC",
        "Proposed solver",
    ):
        assert tool.lower() in docs.lower()
        assert tool.lower() in paper.lower()
    assert "Not documented" in docs
    assert "not a performance benchmark" in docs
    assert "not intended to replace a launcher" in docs
    assert "outperforming" in paper
    assert "tabularx" in latex
