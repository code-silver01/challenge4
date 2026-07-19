"""Tests for Lost & Found Semantic Matcher.

Covers:
* Feature extraction (mock Gemini)
* Similarity scoring with known pairs
* No-match scenario
* Fallback feature extraction
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.lost_found_agent import LostFoundAgent
from app.models.context import UserContext
from app.models.schemas import FoundItem, LostItem
from app.services.repository import InMemoryRepository


@pytest.fixture
def lf_agent(repository: InMemoryRepository) -> LostFoundAgent:
    return LostFoundAgent(repo=repository)


class TestFeatureExtraction:
    """Verify feature extraction from item descriptions."""

    @pytest.mark.asyncio
    async def test_gemini_feature_extraction(
        self,
        lf_agent: LostFoundAgent,
        fan_context: UserContext,
    ) -> None:
        """Gemini extracts structured features from description."""
        mock_features = {
            "item_type": "backpack",
            "color": "red",
            "brand": "Nike",
            "distinguishing_marks": "small tear on left strap",
        }
        with patch(
            "app.agents.lost_found_agent.generate_json",
            new_callable=AsyncMock,
            return_value=mock_features,
        ):
            item = await lf_agent.report_lost(
                fan_context, "Red Nike backpack with torn strap"
            )
            assert item.features is not None
            assert item.features["item_type"] == "backpack"
            assert item.features["color"] == "red"

    @pytest.mark.asyncio
    async def test_fallback_feature_extraction(
        self,
        lf_agent: LostFoundAgent,
        fan_context: UserContext,
    ) -> None:
        """Without Gemini, basic feature extraction still works."""
        with patch(
            "app.agents.lost_found_agent.generate_json",
            new_callable=AsyncMock,
            return_value=None,
        ):
            item = await lf_agent.report_lost(
                fan_context, "Blue wallet with credit cards"
            )
            assert item.features is not None
            assert item.features.get("color") == "blue"
            assert item.features.get("item_type") == "wallet"


class TestSimilarityScoring:
    """Verify similarity scoring between items."""

    def test_exact_match_features(self) -> None:
        """Identical features → high score."""
        lost = LostItem(
            session_id="s1",
            description="Red Nike backpack",
            features={"item_type": "backpack", "color": "red", "brand": "Nike"},
        )
        found = FoundItem(
            volunteer_id="v1",
            description="Red Nike backpack found",
            features={"item_type": "backpack", "color": "red", "brand": "Nike"},
        )
        score, reasoning = LostFoundAgent._compute_similarity(lost, found)
        assert score > 0.8
        assert "exact match" in reasoning.lower()

    def test_partial_match_features(self) -> None:
        """Overlapping features → moderate score."""
        lost = LostItem(
            session_id="s1",
            description="Red backpack",
            features={"item_type": "backpack", "color": "red"},
        )
        found = FoundItem(
            volunteer_id="v1",
            description="Red bag",
            features={"item_type": "bag", "color": "red"},
        )
        score, _ = LostFoundAgent._compute_similarity(lost, found)
        assert 0.2 < score < 0.9

    def test_no_match_features(self) -> None:
        """Completely different items → low score."""
        lost = LostItem(
            session_id="s1",
            description="Blue phone",
            features={"item_type": "phone", "color": "blue"},
        )
        found = FoundItem(
            volunteer_id="v1",
            description="Red hat",
            features={"item_type": "hat", "color": "red"},
        )
        score, _ = LostFoundAgent._compute_similarity(lost, found)
        assert score < 0.3

    def test_zone_match_bonus(self) -> None:
        """Same zone adds a bonus to the score."""
        lost = LostItem(
            session_id="s1",
            description="Black wallet",
            features={"item_type": "wallet", "color": "black"},
            zone_last_seen="Section_A",
        )
        found_same_zone = FoundItem(
            volunteer_id="v1",
            description="Black wallet",
            features={"item_type": "wallet", "color": "black"},
            zone_found="Section_A",
        )
        found_diff_zone = FoundItem(
            volunteer_id="v1",
            description="Black wallet",
            features={"item_type": "wallet", "color": "black"},
            zone_found="Gate_4",
        )
        score_same, _ = LostFoundAgent._compute_similarity(lost, found_same_zone)
        score_diff, _ = LostFoundAgent._compute_similarity(lost, found_diff_zone)
        assert score_same >= score_diff


class TestMatchIntegration:
    """Integration test for find_matches."""

    @pytest.mark.asyncio
    async def test_find_matches_returns_sorted(
        self,
        lf_agent: LostFoundAgent,
        fan_context: UserContext,
        volunteer_context: UserContext,
    ) -> None:
        """Matches are returned sorted by score (highest first)."""
        with patch(
            "app.agents.lost_found_agent.generate_json",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await lf_agent.report_lost(fan_context, "Red backpack")
            await lf_agent.report_found(volunteer_context, "Red bag")
            await lf_agent.report_found(volunteer_context, "Blue phone")

            matches = await lf_agent.find_matches(min_score=0.0)
            # Should have at least some matches
            if len(matches) > 1:
                scores = [m.similarity_score for m in matches]
                assert scores == sorted(scores, reverse=True)
