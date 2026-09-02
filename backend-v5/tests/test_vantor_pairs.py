"""Pins the pre/post pairing to the pairs verified by hand on 1 Sep 2026.

The pairing rule is a heuristic; this table is the ground truth it exists to
reproduce. If a rule change ever moves a site to a different scene, that is a
claim about the imagery and it fails here rather than shipping quietly.
"""
from app.services import vantor_service

EXPECTED = {
    "rasuwagadhi": (("10300100C86CED00", "2021-10-16", 22),
                    ("B040001100881610", "2026-08-27", 71)),
    "timure": (("10300100C86CED00", "2021-10-16", 22),
               ("B040001100881610", "2026-08-27", 71)),
    "syabrubesi": (("10300100C86CED00", "2021-10-16", 22),
                   ("B040001100881610", "2026-08-27", 71)),
    "betrawati": (("10300100FCB83600", "2024-05-29", 15),
                  ("B030001100CF1210", "2026-08-28", 74)),
    "trishuli_bazar": (("10300100FCB83600", "2024-05-29", 15),
                       ("B030001100CF1210", "2026-08-28", 74)),
    # No post-event pass exists over the collapse origin. The absence is part of
    # the record, so it is asserted, not tolerated.
    "langtang_origin": (("10500100364E8400", "2023-09-17", 46), None),
}


def _shape(scene):
    if scene is None:
        return None
    return scene["id"], scene["datetime"][:10], scene["cloud"]


def test_manifest_holds_sixteen_scenes():
    assert len(vantor_service._manifest_items()) == 16


def test_pairs_match_the_verified_table():
    pairs = {p["key"]: p for p in
             vantor_service.compute_pairs(vantor_service._manifest_items())}
    assert set(pairs) == set(EXPECTED)
    for key, (pre, post) in EXPECTED.items():
        assert _shape(pairs[key]["pre"]) == pre, key
        assert _shape(pairs[key]["post"]) == post, key


def test_phase_boundary_is_the_event_day():
    items = vantor_service._manifest_items()
    for item in items:
        expected = "post" if item["datetime"][:10] >= "2026-08-26" else "pre"
        assert item["phase"] == expected, item["id"]


def test_coverage_is_recomputed_from_the_footprint_not_the_bbox():
    """The vendored `covers` lists must survive being derived again."""
    for item in vantor_service._manifest_items():
        assert vantor_service._covered_sites(item["geometry"]) == item["covers"], item["id"]
