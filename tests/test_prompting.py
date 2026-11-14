from pathlib import Path
from datetime import datetime, timedelta, timezone

from src.ai.prompting.enrichment import (
    artifact_prompt,
    block_prompt,
    item_context,
    tool_planning_prompt,
)
from src.timestamps import within_collection_window
from src.models import (
    ClassificationResult,
    ContentAnalysis,
    ContentItem,
    ProcessingResult,
    SourceType,
)
from src.processing import ProfileRegistry


PROFILES = ProfileRegistry.load(
    Path(__file__).resolve().parents[1] / "profiles", "tech-news"
)


def test_tool_planning_excludes_profile_writing_policy():
    profile = PROFILES.get("tech-news")
    blocks = profile.definition.enrichment.blocks

    planning = tool_planning_prompt(blocks)
    artifact = artifact_prompt(profile, "en", blocks)
    block = block_prompt(profile, "en", blocks[0], include_header=True)

    assert profile.enrichment_prompt not in planning
    assert profile.enrichment_prompt in artifact
    assert profile.enrichment_prompt in block
    assert all(configured.id in planning for configured in blocks)
    assert "Block `background` is required" in planning
    assert "history_search" in planning
    assert "at most 3 short results" in planning
    assert "Request at most one history search per item" in planning


def test_enrichment_context_uses_profile_content_budget():
    profile = PROFILES.get("tech-blog")
    item = ContentItem(
        id="rss:test:blog",
        source_type=SourceType.RSS,
        title="Long article",
        url="https://example.com/blog",
        published_at=datetime.now(timezone.utc),
        profile="tech-blog",
        content="OPENING" + "A" * 25000 + "MIDDLE" + "B" * 25000 + "ENDING",
        processing=ProcessingResult(
            classification=ClassificationResult(
                profile="tech-blog", method="source_override"
            ),
            analysis=ContentAnalysis(
                score=8,
                reason="Deep article",
                summary="A long argument",
            ),
        ),
    )

    context = item_context(item, profile, include_content=True)

    assert "[Opening excerpt]" in context
    assert "[Middle excerpt]" in context
    assert "[Closing excerpt]" in context
    assert "OPENING" in context
    assert "MIDDLE" in context
    assert "ENDING" in context


def test_item_context_shows_beijing_clock_for_a_utc_instant():
    profile = PROFILES.get("finance-news")
    item = ContentItem(
        id="rss:test:clock",
        source_type=SourceType.RSS,
        title="Clock",
        url="https://example.com/clock",
        published_at=datetime(2026, 11, 14, 10, 54, tzinfo=timezone.utc),
    )

    context = item_context(item, profile, include_content=False)

    assert "Published (UTC): 2026-11-14T10:54:00+00:00" in context
    assert "Published (Asia/Shanghai): 11月14日 18:54 北京时间" in context


def test_finance_profile_keeps_personnel_wording_and_drops_web_search():
    profile = PROFILES.get("finance-news")
    text = "\n".join([
        profile.analysis_prompt,
        profile.enrichment_prompt,
    ])
    assert "辞职" in text and "被解职" in text
    assert "24 hours" in text
    assert "does not guarantee" in text
    assert all(block.tools == [] for block in profile.definition.enrichment.blocks)


def test_collection_window_drops_items_older_than_cutoff():
    now = datetime(2026, 11, 14, 11, 26, tzinfo=timezone.utc)
    since = now - timedelta(hours=24)
    assert within_collection_window(
        datetime(2026, 11, 14, 10, 54, tzinfo=timezone.utc), since
    )
    assert not within_collection_window(
        datetime(2026, 11, 12, 16, 0, tzinfo=timezone.utc), since
    )
