from __future__ import annotations

import json

from google import genai
from google.genai import types

from app.core.config import settings


class GeminiService:
    """Provider wrapper for safe content generation.

    Gemini can generate ideas, angles and drafts, but it never has permission
    to publish or perform any external LinkedIn action.
    """

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model

    async def generate_json(
        self,
        system_instruction: str,
        prompt: str,
        *,
        max_output_tokens: int = 1800,
    ) -> dict:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                max_output_tokens=max_output_tokens,
            ),
        )
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemini returned invalid JSON.") from exc


    async def research_json(self, system_instruction: str, prompt: str) -> tuple[dict, dict]:
        """Run a web-grounded Gemini request and preserve citation metadata.

        Google Search grounding lets Gemini search current public web content and
        returns grounding chunks/queries alongside the model response.
        """
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                max_output_tokens=2600,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini research returned an empty response.")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemini research returned invalid JSON.") from exc

        metadata: dict = {"queries": [], "sources": []}
        try:
            candidate = response.candidates[0]
            grounding = getattr(candidate, "grounding_metadata", None)
            if grounding:
                metadata["queries"] = list(getattr(grounding, "web_search_queries", None) or [])
                for chunk in list(getattr(grounding, "grounding_chunks", None) or []):
                    web = getattr(chunk, "web", None)
                    if web:
                        metadata["sources"].append(
                            {
                                "title": getattr(web, "title", None),
                                "url": getattr(web, "uri", None),
                            }
                        )
        except Exception:
            # A valid model response should remain usable even if SDK metadata
            # shape changes; citation metadata is additive, not the sole output.
            pass

        return parsed, metadata

    async def create_post(
        self,
        *,
        profile: dict,
        topic: str,
        pillar: str,
        objective: str,
        evidence: list[dict],
        voice: dict,
    ) -> dict:
        system = """You are the writing engine for a professional LinkedIn personal-brand assistant.
Create useful, credible content for a real person.

Hard rules:
- Never invent the user's experiences, achievements, credentials, metrics, clients, employers, opinions, or first-hand observations.
- Do not present model knowledge as newly researched fact.
- Treat brand_intelligence as durable instructions about the user's identity, expertise, audience, themes and writing patterns.
- Use historical_examples to learn structure, specificity, pacing and voice; do not copy their sentences or pretend a historical example is a new experience.
- Prefer the user's observed themes and real experience signals over generic technology commentary.
- Do not force every post to mention AI, automation or technology unless the supplied brand context supports it.
- Avoid generic hooks, motivational filler, broad 'future of work' commentary and obvious AI-generated phrasing.
- If a claim is not supported by supplied evidence or profile context, phrase it as a general observation or omit it.
- Do not use generic AI-marketing language.
- Do not use fake quotations.
- Do not use hashtags unless they materially help.
- Keep the post human, specific, practical, and concise.
- Return JSON only."""
        prompt = json.dumps(
            {
                "profile": profile,
                "topic": topic,
                "pillar": pillar,
                "objective": objective,
                "evidence": evidence,
                "voice": voice,
                "generation_rules": {
                    "use_brand_memory": true,
                    "use_historical_examples_as_style_reference_only": true,
                    "never_copy_historical_sentences": true,
                    "never_invent_personal_experience": true,
                },
                "output_schema": {
                    "title": "short internal title",
                    "angle": "one sentence describing the point of view",
                    "body": "LinkedIn post text, normally 120-280 words",
                    "claims": [
                        {
                            "text": "claim made in the post",
                            "support": "evidence index or profile context or general observation",
                        }
                    ],
                    "confidence": "high|medium|low",
                },
            },
            ensure_ascii=False,
        )
        return await self.generate_json(system, prompt)
