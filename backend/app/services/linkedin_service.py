"""
LinkedIn Auto-Post Service
==========================
Reusable, isolated service for posting job listings to a LinkedIn company page.

Key design principles:
- Non-blocking: all failures are swallowed and logged; job creation always succeeds.
- Feature-flagged: controlled by ENABLE_LINKEDIN_POSTING env var (default: false).
- Stateless: no DB dependency; accepts plain data, returns nothing.
- Production-safe: credentials read strictly from env vars, never hard-coded.

LinkedIn UGC Post API Reference:
  https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/ugc-post-api
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config helpers (read-only at call time so hot-reload / test override works)
# ---------------------------------------------------------------------------

def _is_enabled() -> bool:
    return os.getenv("ENABLE_LINKEDIN_POSTING", "false").strip().lower() == "true"

def _get_access_token() -> str:
    return os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()

def _get_organization_id() -> str:
    """LinkedIn organization URN numeric ID (digits only, not the full URN)."""
    return os.getenv("LINKEDIN_ORGANIZATION_ID", "").strip()


# ---------------------------------------------------------------------------
# Post builder
# ---------------------------------------------------------------------------

def _build_post_text(
    title: str,
    location: str | None,
    experience_level: str | None,
    apply_url: str,
) -> str:
    """Compose human-readable post text from job fields."""
    lines = [f"🚀 We're Hiring: {title}"]

    if location:
        lines.append(f"📍 Location: {location}")

    if experience_level:
        exp_map = {
            "intern": "Internship",
            "junior": "Junior (0–2 yrs)",
            "mid": "Mid-Level (2–5 yrs)",
            "senior": "Senior (5+ yrs)",
            "lead": "Lead / Principal",
        }
        readable = exp_map.get(experience_level.lower(), experience_level.title())
        lines.append(f"🎯 Experience: {readable}")

    lines.append(f"\n🔗 Apply here: {apply_url}")
    lines.append("\n#Hiring #Jobs #Careers #Recruitment")

    return "\n".join(lines)


def _build_ugc_payload(text: str, organization_id: str) -> dict:
    """Build the LinkedIn UGC Post API request body."""
    return {
        "author": f"urn:li:organization:{organization_id}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": text
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def post_job_to_linkedin(
    *,
    job_id: str,
    title: str,
    location: str | None = None,
    experience_level: str | None = None,
    frontend_base_url: str = "http://localhost:3000",
) -> None:
    """
    Fire-and-forget: post a new job opening to the LinkedIn company page.

    This function MUST be called AFTER the job is successfully committed to
    the database. It will silently log and return on any failure — it must
    never raise, so the caller's success flow is never interrupted.

    Parameters
    ----------
    job_id        : The public job identifier (e.g. "JOB-ABC123")
    title         : Job title
    location      : Optional location string
    experience_level : Optional experience level key (e.g. "junior", "senior")
    frontend_base_url : Base URL of the frontend for constructing the apply link
    """
    # --- Gate 1: feature flag ---
    if not _is_enabled():
        logger.debug("[LinkedIn] Posting disabled (ENABLE_LINKEDIN_POSTING != true). Skipping.")
        return

    try:
        access_token = _get_access_token()
        organization_id = _get_organization_id()

        # --- Gate 2: credential check ---
        if not access_token:
            logger.warning("[LinkedIn] LINKEDIN_ACCESS_TOKEN not set. Cannot post job.")
            return
        if not organization_id:
            logger.warning("[LinkedIn] LINKEDIN_ORGANIZATION_ID not set. Cannot post job.")
            return

        # Build the apply link
        apply_url = f"{frontend_base_url.rstrip('/')}/jobs/{job_id}"

        post_text = _build_post_text(
            title=title,
            location=location,
            experience_level=experience_level,
            apply_url=apply_url,
        )

        payload = _build_ugc_payload(post_text, organization_id)

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        response = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            json=payload,
            headers=headers,
            timeout=10,
        )

        if response.status_code in (200, 201):
            post_id = response.headers.get("x-restli-id", "unknown")
            logger.info(
                f"[LinkedIn] Job post published successfully. "
                f"job_id={job_id} title='{title}' linkedin_post_id={post_id}"
            )
        else:
            logger.warning(
                f"[LinkedIn] API returned non-2xx status. "
                f"status={response.status_code} body={response.text[:300]} job_id={job_id}"
            )

    except requests.exceptions.Timeout:
        logger.warning(f"[LinkedIn] Request timed out while posting job_id={job_id}. Skipping.")
    except requests.exceptions.ConnectionError:
        logger.warning(f"[LinkedIn] Connection error while posting job_id={job_id}. Skipping.")
    except Exception as exc:
        # Catch-all: never let LinkedIn failure surface to the caller
        logger.error(
            f"[LinkedIn] Unexpected error posting job_id={job_id}: {exc}",
            exc_info=True,
        )
