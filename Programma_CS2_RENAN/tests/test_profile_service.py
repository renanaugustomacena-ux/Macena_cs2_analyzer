"""
Tests for Profile Service — Phase 8 Coverage Expansion.

Covers:
  ProfileService — input validation, fetch_steam_stats/fetch_faceit_stats guard logic
  _parse_steam_response — Steam API response parsing
  _apply_profile_fields — Profile field update helper
"""

import sys


from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# ProfileService input validation
# ---------------------------------------------------------------------------
class TestProfileServiceGuards:
    """Tests for input validation guards in ProfileService."""

    def _make_service(self, steam_key="", faceit_key=""):
        from Programma_CS2_RENAN.backend.services.profile_service import ProfileService
        svc = ProfileService.__new__(ProfileService)
        svc.steam_key = steam_key
        svc.faceit_key = faceit_key
        return svc

    def test_fetch_steam_no_key(self):
        svc = self._make_service(steam_key="")
        result = svc.fetch_steam_stats("76561198012345678")
        assert "error" in result

    def test_fetch_steam_no_steam_id(self):
        svc = self._make_service(steam_key="ABCDEF123")
        result = svc.fetch_steam_stats("")
        assert "error" in result

    def test_fetch_faceit_no_key(self):
        svc = self._make_service(faceit_key="")
        result = svc.fetch_faceit_stats("testplayer")
        assert "error" in result


# ---------------------------------------------------------------------------
# _parse_steam_response
# ---------------------------------------------------------------------------
class TestParseSteamResponse:
    """Tests for Steam API response parsing."""

    def _parse(self, resp, key="k", steam_id="12345"):
        from Programma_CS2_RENAN.backend.services.profile_service import _parse_steam_response
        return _parse_steam_response(resp, key, steam_id)

    def test_player_not_found(self):
        result = self._parse({"response": {"players": []}})
        assert result["error"] == "Player not found"

    def test_missing_response_key(self):
        result = self._parse({})
        assert result["error"] == "Player not found"

    def test_none_players(self):
        result = self._parse({"response": {}})
        assert result["error"] == "Player not found"

    @patch("Programma_CS2_RENAN.backend.services.profile_service._fetch_cs2_hours", return_value=1500.0)
    def test_valid_response(self, mock_hours):
        resp = {
            "response": {
                "players": [
                    {
                        "personaname": "TestPlayer",
                        "avatarfull": "https://example.com/avatar.jpg",
                    }
                ]
            }
        }
        result = self._parse(resp)
        assert result["nickname"] == "TestPlayer"
        assert result["avatar"] == "https://example.com/avatar.jpg"
        assert result["playtime_forever"] == 1500.0

    @patch("Programma_CS2_RENAN.backend.services.profile_service._fetch_cs2_hours", return_value=0)
    def test_missing_fields(self, mock_hours):
        resp = {"response": {"players": [{}]}}
        result = self._parse(resp)
        assert result["nickname"] is None
        assert result["avatar"] is None
        assert result["playtime_forever"] == 0


# ---------------------------------------------------------------------------
# _apply_profile_fields
# ---------------------------------------------------------------------------
class TestApplyProfileFields:
    """Tests for profile field application helper."""

    def test_apply_fields(self):
        from Programma_CS2_RENAN.backend.services.profile_service import _apply_profile_fields

        class FakeProfile:
            def model_dump(self, exclude_unset=False):
                return {
                    "id": 1,
                    "player_name": "NewName",
                    "steam_id": "12345",
                    "faceit_elo": 2000,
                }

        class Existing:
            player_name = "OldName"
            steam_id = "00000"
            faceit_elo = 1500

        existing = Existing()
        profile = FakeProfile()
        _apply_profile_fields(existing, profile)
        assert existing.player_name == "NewName"
        assert existing.steam_id == "12345"
        assert existing.faceit_elo == 2000

    def test_id_not_overwritten(self):
        from Programma_CS2_RENAN.backend.services.profile_service import _apply_profile_fields

        class FakeProfile:
            def model_dump(self, exclude_unset=False):
                return {"id": 999, "player_name": "Test"}

        class Existing:
            id = 1
            player_name = "Old"

        existing = Existing()
        _apply_profile_fields(existing, FakeProfile())
        assert existing.id == 1  # id should NOT be overwritten
        assert existing.player_name == "Test"
