import unittest

from app.agents.research import ResearchService, _candidate_similarity, _profile_relevance, _tokens, _weighted_profile_terms
from app.models.models import ContentOpportunity, UserProfile, LearningEvent
from app.agents.strategy import ContentStrategyService
from app.agents.voice import VoiceProfileBuilder


class TestMVPAgents(unittest.TestCase):
    def test_strategy_service_recommends_content_mix(self):
        strategy = ContentStrategyService()
        recommendations = strategy.recommend(focus="build authority in AI adoption for senior product leaders")

        self.assertIn("content_mix", recommendations)
        self.assertIn("content_calendar", recommendations)
        self.assertGreater(len(recommendations["content_mix"]), 0)
        self.assertGreater(len(recommendations["content_calendar"]), 0)

    def test_voice_profile_builder_creates_style_profile(self):
        builder = VoiceProfileBuilder()
        profile = builder.learn(
            approved_examples=[
                "I’ve learned this the hard way: simple systems beat clever complexity.",
                "Most teams over-invest in tools and under-invest in alignment.",
            ]
        )

        self.assertIn("tone", profile)
        self.assertIn("preferred_phrases", profile)
        self.assertIn("avoid_phrases", profile)
        self.assertTrue(profile["preferred_phrases"])

    def test_personal_thought_event_is_distinct_learning_signal(self):
        event = LearningEvent(
            profile_id=7,
            event_type="USER_THOUGHT",
            source_type="manual_thought",
            content="I believe practical AI adoption starts with workflow redesign.",
            metadata_json='{"title":"AI adoption lesson","topic":"AI transformation"}',
            status="PENDING",
        )
        self.assertEqual(event.event_type, "USER_THOUGHT")
        self.assertEqual(event.source_type, "manual_thought")
        self.assertEqual(event.status, "PENDING")

    def test_research_service_creates_evidence_pack(self):
        service = ResearchService()
        pack = service.build_evidence_pack(
            topic="AI adoption in enterprise settings",
            sources=[
                {"title": "AI adoption guide", "url": "https://example.com/ai-guide", "summary": "Companies proceed in waves."},
                {"title": "Leadership patterns", "url": "https://example.com/leadership", "summary": "Alignment matters more than hype."},
            ],
        )

        self.assertIn("facts", pack)
        self.assertIn("sources", pack)
        self.assertGreater(len(pack["sources"]), 0)


    def test_research_profile_relevance_uses_user_brand_signals(self):
        profile = UserProfile(
            professional_title="AI transformation strategy leader",
            industry="Enterprise consulting",
            tone="clear",
        )
        brand_memory = {
            "summary": "Helps enterprise leaders adopt AI responsibly.",
            "identity": {"role": ["AI transformation", "strategy"], "industry": ["enterprise consulting"]},
            "expertise": [{"area": "AI adoption"}, {"area": "stakeholder management"}],
            "themes": [{"theme": "responsible AI"}, {"theme": "change management"}],
        }
        terms = _weighted_profile_terms(profile, brand_memory, {}, None)

        relevant = {
            "title": "Responsible AI adoption in enterprise transformation",
            "topic": "AI adoption and stakeholder management",
            "angle": "A practical strategy lens for enterprise leaders",
            "pillar": "AI transformation",
            "objective": "Share practical enterprise strategy",
        }
        unrelated = {
            "title": "Weekend travel trends and airline loyalty",
            "topic": "Consumer travel",
            "angle": "What leisure travelers are buying",
            "pillar": "Travel",
            "objective": "Consumer trends",
        }

        relevant_score = _profile_relevance(relevant, terms, None)
        unrelated_score = _profile_relevance(unrelated, terms, None)

        self.assertGreater(relevant_score, unrelated_score)
        self.assertGreater(relevant_score, 40)
        self.assertLessEqual(relevant_score, 100)

    def test_research_candidate_similarity_deduplicates_same_topic(self):
        first = {"title": "AI adoption in enterprise consulting", "topic": "AI adoption"}
        second = {"title": "Enterprise consulting AI adoption", "topic": "AI adoption"}
        different = {"title": "Project governance lessons", "topic": "Stakeholder management"}

        self.assertGreaterEqual(_candidate_similarity(first, second), 0.72)
        self.assertLess(_candidate_similarity(first, different), 0.72)

    def test_research_serialization_includes_original_source_links(self):
        item = ContentOpportunity(
            id=42,
            profile_id=7,
            title="AI adoption",
            topic="AI adoption",
            angle="Practical lens",
            pillar="AI transformation",
            format="Insight post",
            objective="Build authority",
            status="RANKED",
            total_score=82.5,
            research_source_ids_json="[101]",
            evidence_json='{"source_urls":["https://example.com/original"]}',
        )
        serialized = ResearchService().serialize(
            item,
            sources=[{
                "title": "Original publisher",
                "url": "https://example.com/original",
                "domain": "example.com",
            }],
        )

        self.assertEqual(serialized["sources"][0]["url"], "https://example.com/original")
        self.assertEqual(serialized["source_ids"], [101])


if __name__ == "__main__":
    unittest.main()
