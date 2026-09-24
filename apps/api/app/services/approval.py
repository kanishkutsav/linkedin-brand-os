from datetime import datetime, timezone, timedelta
import hashlib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import ApprovalRequest, ContentVersion, ContentItem, UserProfile, VoiceMemory, AuditLog, SystemFlag, FeedbackEntry, HistoricalPost
from app.core.config import settings
from app.services.brand_intelligence import BrandIntelligenceService
from app.services.gemini_service import ModelRouterService
from app.guards.guardrails import run_content_guards


class ApprovalService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def request(self, version: ContentVersion, action_type: str = "PUBLISH_POST"):
        approval = ApprovalRequest(
            content_version_id=version.id,
            action_type=action_type,
            status="PENDING",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.approval_ttl_minutes),
        )
        self.session.add(approval)
        self.session.add(AuditLog(event_type="APPROVAL_REQUESTED", actor="system", payload=f"version={version.id}"))
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def list_pending(self):
        result = await self.session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status.in_(["PENDING", "EDITED", "REGENERATED"]),
                (ApprovalRequest.expires_at.is_(None)) | (ApprovalRequest.expires_at > datetime.now(timezone.utc)),
            )
        )
        return result.scalars().all()

    async def approve(self, approval_id: int):
        approval = await self.session.get(ApprovalRequest, approval_id)
        if not approval or approval.status not in {"PENDING", "EDITED", "REGENERATED"}:
            raise ValueError("Approval is not in an approvable state")
        if approval.expires_at and approval.expires_at <= datetime.now(timezone.utc):
            approval.status = "EXPIRED"
            await self.session.commit()
            raise ValueError("Approval has expired")
        version = await self.session.get(ContentVersion, approval.content_version_id)
        if not version:
            raise ValueError("Content version not found")
        guard = run_content_guards(version.body)
        if not guard.passed:
            raise ValueError("Approval blocked by guardrails: " + "; ".join(guard.issues))
        token = hashlib.sha256(f"{approval.id}:{version.content_hash}".encode()).hexdigest()
        approval.status = "APPROVED"
        approval.approval_hash = token
        approval.approved_at = datetime.now(timezone.utc)
        self.session.add(AuditLog(event_type="APPROVAL_GRANTED", actor="user", payload=f"approval={approval.id}"))
        self.session.add(
            FeedbackEntry(
                approval_id=approval.id,
                content_version_id=version.id,
                action="APPROVED",
                reason="User approved the content.",
                payload=f"approval={approval.id}",
            )
        )
        await self.session.commit()
        return approval

    async def edit(self, approval_id: int, edited_body: str, reason: str | None = None):
        approval = await self.session.get(ApprovalRequest, approval_id)
        if not approval or approval.status not in {"PENDING", "EDITED", "REGENERATED"}:
            raise ValueError("Approval is not editable in its current state")
        if approval.expires_at and approval.expires_at <= datetime.now(timezone.utc):
            approval.status = "EXPIRED"
            await self.session.commit()
            raise ValueError("Approval has expired")
        edited_body = (edited_body or "").strip()
        guard = run_content_guards(edited_body)
        if not guard.passed:
            raise ValueError("Edit blocked by guardrails: " + "; ".join(guard.issues))
        version = await self.session.get(ContentVersion, approval.content_version_id)
        if not version:
            raise ValueError("Content version not found")
        new_hash = hashlib.sha256(edited_body.encode("utf-8")).hexdigest()
        version.body = edited_body
        version.content_hash = new_hash
        version.version_number += 1
        approval.status = "EDITED"
        approval.edited_body = edited_body
        approval.reason = reason or "Content was edited by the human reviewer."
        self.session.add(
            FeedbackEntry(
                approval_id=approval.id,
                content_version_id=version.id,
                action="EDITED",
                reason=approval.reason,
                payload=edited_body,
            )
        )
        self.session.add(AuditLog(event_type="APPROVAL_EDITED", actor="user", payload=f"approval={approval.id}"))
        await self.session.commit()
        return approval

    async def reject(self, approval_id: int, reason: str | None = None):
        approval = await self.session.get(ApprovalRequest, approval_id)
        if not approval:
            raise ValueError("Approval not found")
        if approval.status == "EXECUTED":
            raise ValueError("Published content cannot be rejected from the approval workflow.")
        approval.status = "REJECTED"
        approval.reason = reason or "Rejected by human reviewer."
        version = await self.session.get(ContentVersion, approval.content_version_id)
        self.session.add(
            FeedbackEntry(
                approval_id=approval.id,
                content_version_id=version.id if version else None,
                action="REJECTED",
                reason=approval.reason,
                payload="rejected",
            )
        )
        self.session.add(AuditLog(event_type="APPROVAL_REJECTED", actor="user", payload=f"approval={approval.id}"))
        await self.session.commit()
        return approval

    async def regenerate(self, approval_id: int, feedback: str | None = None):
        approval = await self.session.get(ApprovalRequest, approval_id)
        if not approval or approval.status not in {"PENDING", "EDITED", "REGENERATED"}:
            raise ValueError("Approval is not regenerable in its current state")
        if approval.expires_at and approval.expires_at <= datetime.now(timezone.utc):
            approval.status = "EXPIRED"
            await self.session.commit()
            raise ValueError("Approval has expired")
        version = await self.session.get(ContentVersion, approval.content_version_id)
        if not version:
            raise ValueError("Content version not found")

        # Regeneration is grounded in the same Brand DNA and current draft.
        # Reviewer feedback is an explicit instruction, not an optional log entry.
        item = await self.session.get(ContentItem, version.content_id)
        profile = await self.session.get(UserProfile, 1)
        if not profile:
            raise ValueError("Brand profile not found")

        brand_context = await BrandIntelligenceService(self.session).generation_context(profile.id)
        voice_result = await self.session.execute(select(VoiceMemory).where(VoiceMemory.profile_id == profile.id).limit(1))
        voice = voice_result.scalar_one_or_none()
        voice_context = {
            "tone": voice.tone if voice else profile.tone,
            "sentence_style": voice.sentence_style if voice else "clear and grounded",
            "vocabulary": voice.vocabulary if voice else "",
            "preferred_phrases": voice.preferred_phrases if voice else "",
            "avoid_phrases": voice.avoid_phrases if voice else "",
            "emoji_usage": voice.emoji_usage if voice else "limited",
            "humor_style": voice.humor_style if voice else "",
            "technical_depth": voice.technical_depth if voice else "moderate",
            "opinion_style": voice.opinion_style if voice else "grounded in observed content",
            "storytelling_style": voice.storytelling_style if voice else "concrete",
        }
        generated = await ModelRouterService().create_post(
            profile={
                "display_name": profile.display_name,
                "professional_title": profile.professional_title,
                "industry": profile.industry,
                "audience": profile.audience,
                "goals": profile.goals,
                "brand_positioning": profile.brand_positioning,
                "tone": profile.tone,
                "brand_intelligence": brand_context,
            },
            topic=item.topic if item else "Professional insight",
            pillar=item.pillar if item else "Expertise",
            objective="Regenerate the current LinkedIn draft using the reviewer's feedback while preserving the user's meaning and factual boundaries.",
            evidence=[],
            voice=voice_context,
            feedback=(feedback or "").strip() or None,
            current_draft=version.body,
        )

        new_body = str(generated.get("body") or "").strip()
        if not new_body:
            raise ValueError("The configured content model did not return a usable regenerated draft.")

        guard = run_content_guards(new_body)
        if not guard.passed:
            raise ValueError("Regenerated content blocked by guardrails: " + "; ".join(guard.issues))

        version.body = new_body
        version.content_hash = hashlib.sha256(new_body.encode("utf-8")).hexdigest()
        version.version_number += 1
        approval.status = "REGENERATED"
        approval.reason = (feedback or "").strip() or "Regenerated using the saved Brand DNA."

        self.session.add(
            FeedbackEntry(
                approval_id=approval.id,
                content_version_id=approval.content_version_id,
                action="REGENERATED",
                reason=approval.reason,
                payload=new_body,
            )
        )
        self.session.add(AuditLog(
            event_type="APPROVAL_REGENERATED",
            actor="system",
            payload=f"approval={approval.id};feedback={(feedback or '').strip()[:500]}",
        ))
        await self.session.commit()
        return approval

    async def execute(self, approval_id: int, adapter):
        approval = await self.session.get(ApprovalRequest, approval_id)
        if not approval or approval.status != "APPROVED": raise ValueError("Valid approval required")
        if approval.expires_at and approval.expires_at < datetime.now(timezone.utc):
            approval.status = "EXPIRED"
            await self.session.commit()
            raise ValueError("Approval has expired")
        if settings.emergency_stop: raise ValueError("Emergency stop is active")
        flags = (await self.session.execute(select(SystemFlag))).scalars().first()
        if flags and flags.emergency_stop: raise ValueError("Emergency stop is active")
        version = await self.session.get(ContentVersion, approval.content_version_id)
        if not version:
            raise ValueError("Content version not found")
        guard = run_content_guards(version.body)
        if not guard.passed:
            raise ValueError("Publishing blocked by guardrails: " + "; ".join(guard.issues))
        expected = hashlib.sha256(f"{approval.id}:{version.content_hash}".encode()).hexdigest()
        if approval.approval_hash != expected: raise ValueError("Approval token/content hash mismatch")
        result = adapter.publish_post(version.body)
        approval.status = "EXECUTED" if result.success else "FAILED"

        # A successfully published Brand OS post becomes durable first-party
        # brand evidence. This is the automatic learning path for content created
        # and published through the product; arbitrary LinkedIn scraping is never used.
        if result.success:
            digest = hashlib.sha256(version.body.encode("utf-8")).hexdigest()
            existing = await self.session.execute(
                select(HistoricalPost).where(
                    HistoricalPost.profile_id == 1,
                    HistoricalPost.content_hash == digest,
                )
            )
            if existing.scalar_one_or_none() is None:
                self.session.add(
                    HistoricalPost(
                        profile_id=1,
                        external_id=result.external_id,
                        body=version.body,
                        content_hash=digest,
                        published_at=datetime.now(timezone.utc),
                        source="brand_os_publish",
                        metadata_json=f'{{"approval_id": {approval.id}, "content_version_id": {version.id}}}',
                    )
                )

        self.session.add(AuditLog(event_type="ACTION_EXECUTED", actor="action-executor", payload=f"approval={approval.id};result={result.message}"))
        await self.session.commit()
        return result
