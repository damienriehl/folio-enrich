"""Tests for branch_config module."""

import re

from app.services.folio.branch_config import (
    BRANCH_CONFIG,
    EXCLUDED_BRANCHES,
    get_branch_color,
    get_branch_display_name,
)

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class TestBranchConfig:
    def test_has_26_branches(self):
        assert len(BRANCH_CONFIG) == 26

    def test_all_branches_have_valid_hex_colors(self):
        for key, cfg in BRANCH_CONFIG.items():
            assert "color" in cfg, f"Branch {key} missing color"
            assert HEX_COLOR_RE.match(cfg["color"]), (
                f"Branch {key} has invalid hex color: {cfg['color']}"
            )

    def test_all_branches_have_display_names(self):
        for key, cfg in BRANCH_CONFIG.items():
            assert "name" in cfg, f"Branch {key} missing name"
            assert len(cfg["name"]) > 0, f"Branch {key} has empty name"

    def test_excluded_branches_exist(self):
        all_names = {cfg["name"] for cfg in BRANCH_CONFIG.values()}
        # "Standards Compatibility" should be in config but excluded
        assert "Standards Compatibility" in all_names
        assert "Standards Compatibility" in EXCLUDED_BRANCHES

    def test_get_branch_color_known(self):
        color = get_branch_color("Area of Law")
        assert color == "#1a5276"

    def test_get_branch_color_unknown_returns_fallback(self):
        color = get_branch_color("Nonexistent Branch")
        assert color == "#4a5568"

    def test_get_branch_display_name_known(self):
        assert get_branch_display_name("ACTOR_PLAYER") == "Actor / Player"
        assert get_branch_display_name("AREA_OF_LAW") == "Area of Law"

    def test_get_branch_display_name_unknown_returns_key(self):
        assert get_branch_display_name("UNKNOWN_KEY") == "UNKNOWN_KEY"

    def test_no_duplicate_display_names(self):
        names = [cfg["name"] for cfg in BRANCH_CONFIG.values()]
        assert len(names) == len(set(names)), "Duplicate display names found"

    def test_no_duplicate_colors(self):
        colors = [cfg["color"] for cfg in BRANCH_CONFIG.values()]
        assert len(colors) == len(set(colors)), "Duplicate colors found"

    def test_excluded_branches_are_frozenset(self):
        assert isinstance(EXCLUDED_BRANCHES, frozenset)
