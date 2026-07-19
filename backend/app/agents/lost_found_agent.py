"""AI Lost & Found Semantic Matcher.

Fans submit free-text "lost item" descriptions; volunteers submit
"found item" descriptions.  Gemini extracts structured features from
each, and we score similarity between pairs using a lightweight
text-similarity scorer (Jaccard on extracted features).
"""

from __future__ import annotations

import logging
from typing import Optional

from ..models.context import UserContext
from ..models.schemas import FoundItem, LostFoundMatch, LostItem
from ..services.gemini_client import generate_json
from ..services.input_sanitizer import sanitize_input
from ..services.repository import RepositoryInterface, get_repository

logger = logging.getLogger(__name__)

_FEATURE_EXTRACTION_PROMPT = """Extract structured features from this item description for a lost-and-found matching system.

Description: "{description}"
Zone: {zone}

Respond in JSON:
{{
  "item_type": "e.g., backpack, phone, wallet, jacket, hat, sunglasses",
  "color": "primary color(s)",
  "brand": "brand if mentioned, else null",
  "distinguishing_marks": "any unique features, stickers, damage, etc.",
  "size": "small, medium, large if determinable, else null",
  "contents": "notable contents if mentioned, else null"
}}

Only include features that are clearly stated or strongly implied."""


class LostFoundAgent:
    """Semantic lost & found matching via structured feature extraction.

    Usage::

        agent = LostFoundAgent()
        lost = await agent.report_lost(context, "Red Nike backpack, section B")
        found = await agent.report_found(context, "Red bag near gate 2")
        matches = await agent.find_matches()
    """

    def __init__(self, repo: RepositoryInterface | None = None) -> None:
        self._repo = repo or get_repository()

    async def report_lost(
        self,
        context: UserContext,
        description: str,
        zone: str | None = None,
    ) -> LostItem:
        """Report a lost item — extracts features via Gemini.

        Parameters
        ----------
        context:
            The fan's session context.
        description:
            Free-text description of the lost item.
        zone:
            Zone where the item was last seen.

        Returns
        -------
        LostItem
            The stored lost item with extracted features.
        """
        clean_desc = sanitize_input(description)
        actual_zone = zone or context.current_location_node

        features = await self._extract_features(clean_desc, actual_zone)

        item = LostItem(
            session_id=context.session_id,
            description=clean_desc,
            features=features,
            zone_last_seen=actual_zone,
        )
        await self._repo.save_lost_item(item)
        logger.info("Lost item reported: %s", item.item_id)
        return item

    async def report_found(
        self,
        context: UserContext,
        description: str,
        zone: str | None = None,
    ) -> FoundItem:
        """Report a found item — extracts features via Gemini.

        Parameters
        ----------
        context:
            The volunteer's session context.
        description:
            Free-text description of the found item.
        zone:
            Zone where the item was found.

        Returns
        -------
        FoundItem
            The stored found item with extracted features.
        """
        clean_desc = sanitize_input(description)
        actual_zone = zone or context.current_location_node

        features = await self._extract_features(clean_desc, actual_zone)

        item = FoundItem(
            volunteer_id=context.session_id,
            description=clean_desc,
            features=features,
            zone_found=actual_zone,
        )
        await self._repo.save_found_item(item)
        logger.info("Found item reported: %s", item.item_id)
        return item

    async def find_matches(
        self, min_score: float = 0.3
    ) -> list[LostFoundMatch]:
        """Score all lost-found pairs and return matches above threshold.

        Parameters
        ----------
        min_score:
            Minimum similarity score (0-1) to include in results.

        Returns
        -------
        list[LostFoundMatch]
            Matches sorted by similarity (highest first).
        """
        lost_items = await self._repo.get_lost_items(unmatched_only=True)
        found_items = await self._repo.get_found_items(unclaimed_only=True)

        matches: list[LostFoundMatch] = []

        for lost in lost_items:
            for found in found_items:
                score, reasoning = self._compute_similarity(lost, found)
                if score >= min_score:
                    matches.append(
                        LostFoundMatch(
                            lost_item_id=lost.item_id,
                            found_item_id=found.item_id,
                            similarity_score=score,
                            match_reasoning=reasoning,
                        )
                    )

        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        return matches

    async def get_matches_for_item(
        self, item_id: str, is_lost: bool = True
    ) -> list[LostFoundMatch]:
        """Get matches for a specific lost or found item."""
        all_matches = await self.find_matches()
        if is_lost:
            return [m for m in all_matches if m.lost_item_id == item_id]
        return [m for m in all_matches if m.found_item_id == item_id]

    # ── Feature extraction ───────────────────────────────────────────

    async def _extract_features(
        self, description: str, zone: str | None
    ) -> dict:
        """Extract structured features from item description via Gemini."""
        prompt = _FEATURE_EXTRACTION_PROMPT.format(
            description=description,
            zone=zone or "unknown",
        )

        result = await generate_json(prompt, temperature=0.1)
        if result:
            return {k: v for k, v in result.items() if v is not None}

        # Fallback: extract simple features from text
        return self._fallback_features(description)

    @staticmethod
    def _fallback_features(description: str) -> dict:
        """Extract basic features from text without LLM."""
        desc_lower = description.lower()
        features: dict = {}

        # Color detection (word-boundary matching to avoid 'credit' → 'red')
        import re as _re
        colors = [
            "red", "blue", "green", "black", "white", "yellow",
            "orange", "pink", "purple", "brown", "grey", "gray",
        ]
        found_colors = [
            c for c in colors
            if _re.search(rf"\b{c}\b", desc_lower)
        ]
        if found_colors:
            features["color"] = ", ".join(found_colors)

        # Item type detection
        item_types = {
            "backpack": "backpack", "bag": "bag", "phone": "phone",
            "wallet": "wallet", "jacket": "jacket", "hat": "hat",
            "sunglasses": "sunglasses", "keys": "keys", "watch": "watch",
            "camera": "camera", "umbrella": "umbrella", "bottle": "bottle",
            "scarf": "scarf", "flag": "flag", "jersey": "jersey",
        }
        for keyword, item_type in item_types.items():
            if keyword in desc_lower:
                features["item_type"] = item_type
                break

        return features

    # ── Similarity scoring ───────────────────────────────────────────

    @staticmethod
    def _compute_similarity(
        lost: LostItem, found: FoundItem
    ) -> tuple[float, str]:
        """Score similarity between a lost and found item.

        Uses weighted Jaccard-like comparison on extracted features.
        Also considers zone proximity.

        Returns
        -------
        tuple[float, str]
            ``(score_0_to_1, reasoning_text)``
        """
        lost_feat = lost.features or {}
        found_feat = found.features or {}

        if not lost_feat and not found_feat:
            # Compare raw descriptions via word overlap
            lost_words = set(lost.description.lower().split())
            found_words = set(found.description.lower().split())
            if not lost_words or not found_words:
                return 0.0, "Insufficient data for comparison."
            overlap = lost_words & found_words
            # Remove common stop words
            stop = {"a", "an", "the", "my", "i", "in", "at", "near", "lost", "found", "is", "was"}
            overlap -= stop
            union = (lost_words | found_words) - stop
            score = len(overlap) / max(len(union), 1)
            return score, f"Word overlap: {', '.join(overlap) if overlap else 'none'}"

        # Weighted feature comparison
        weights = {
            "item_type": 0.35,
            "color": 0.25,
            "brand": 0.15,
            "distinguishing_marks": 0.10,
            "size": 0.05,
            "contents": 0.10,
        }

        total_score = 0.0
        total_weight = 0.0
        matches: list[str] = []
        mismatches: list[str] = []

        for feature, weight in weights.items():
            lost_val = str(lost_feat.get(feature, "")).lower().strip()
            found_val = str(found_feat.get(feature, "")).lower().strip()

            if not lost_val or not found_val:
                continue  # Skip missing features

            total_weight += weight

            # Partial string matching
            if lost_val == found_val:
                total_score += weight
                matches.append(f"{feature}: exact match ({lost_val})")
            elif lost_val in found_val or found_val in lost_val:
                total_score += weight * 0.7
                matches.append(f"{feature}: partial match ({lost_val} / {found_val})")
            else:
                # Check for word overlap within the feature
                lost_words = set(lost_val.split())
                found_words = set(found_val.split())
                word_overlap = lost_words & found_words
                if word_overlap:
                    total_score += weight * 0.4
                    matches.append(
                        f"{feature}: word overlap ({', '.join(word_overlap)})"
                    )
                else:
                    mismatches.append(f"{feature}: no match ({lost_val} vs {found_val})")

        # Zone proximity bonus
        if (
            lost.zone_last_seen
            and found.zone_found
            and lost.zone_last_seen == found.zone_found
        ):
            total_score += 0.1
            matches.append("zone: same location")

        # Normalise
        final_score = total_score / max(total_weight, 0.01)
        final_score = min(1.0, final_score)

        reasoning_parts = []
        if matches:
            reasoning_parts.append("Matches: " + "; ".join(matches))
        if mismatches:
            reasoning_parts.append("Mismatches: " + "; ".join(mismatches))

        reasoning = " | ".join(reasoning_parts) or "No features to compare."

        return round(final_score, 3), reasoning
