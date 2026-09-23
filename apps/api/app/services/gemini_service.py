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

    async def generate_json(self, system_instruction: str, prompt: str) -> dict:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                max_output_tokens=1800,
            ),
        )
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemini returned invalid JSON.") from exc

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
