import pytest

from modpack_solver.importers.modrinth_url import ModrinthResourceKind, parse_modrinth_url


@pytest.mark.parametrize(
    ("url", "kind", "slug", "version"),
    [
        ("https://modrinth.com/mod/sodium", ModrinthResourceKind.MOD, "sodium", None),
        ("https://modrinth.com/modpack/fabulously-optimized", ModrinthResourceKind.MODPACK, "fabulously-optimized", None),
        ("https://modrinth.com/mod/sodium/version/mc1.20", ModrinthResourceKind.MOD, "sodium", "mc1.20"),
        ("https://www.modrinth.com/modpack/additive/", ModrinthResourceKind.MODPACK, "additive", None),
        ("https://modrinth.com/mod/sodium?ref=test", ModrinthResourceKind.MOD, "sodium", None),
    ],
)
def test_parse_supported_modrinth_urls(url, kind, slug, version):
    parsed = parse_modrinth_url(url)
    assert parsed.kind == kind
    assert parsed.slug == slug
    assert parsed.version == version
    assert parsed.original_url == url


def test_modrinth_url_rejects_other_host():
    with pytest.raises(ValueError, match="modrinth.com"):
        parse_modrinth_url("https://example.com/mod/sodium")


def test_modrinth_url_rejects_unsupported_path():
    with pytest.raises(ValueError, match="Supported"):
        parse_modrinth_url("https://modrinth.com/plugin/example")
