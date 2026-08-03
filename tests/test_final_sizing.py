import pytest

from modpack_solver.final_dataset.sizing import PackSizeCategory, classify_pack_size


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, PackSizeCategory.SMALL),
        (1, PackSizeCategory.SMALL),
        (30, PackSizeCategory.SMALL),
        (31, PackSizeCategory.MEDIUM),
        (80, PackSizeCategory.MEDIUM),
        (81, PackSizeCategory.LARGE),
        (199, PackSizeCategory.LARGE),
        (200, PackSizeCategory.HUGE),
        (500, PackSizeCategory.HUGE),
    ],
)
def test_classify_pack_size_boundaries(count, expected):
    assert classify_pack_size(count) == expected


def test_classify_pack_size_rejects_negative_count():
    with pytest.raises(ValueError, match="negative"):
        classify_pack_size(-1)
