from app.services.jobs import _normalize_apify_job, _dedupe


def test_apify_job_is_normalized_to_shared_jobs_response_shape():
    job = _normalize_apify_job({
        "id": "indeed:123",
        "source": "Indeed",
        "title": "Senior Product Manager",
        "company": "Example Co",
        "location": "Bengaluru, India",
        "experience": "5-8 years",
        "description": "Build products",
        "salary": "₹20L",
        "postedAt": "2026-11-20",
        "applyUrl": "https://example.com/apply",
        "sourceUrl": "https://example.com/job/123",
    })

    assert job["provider"] == "Indeed"
    assert job["provider_job_id"] == "indeed:123"
    assert job["title"] == "Senior Product Manager"
    assert job["company"] == "Example Co"
    assert job["location"] == "Bengaluru, India"
    assert job["experience_level"] == "5-8 years"
    assert job["application_url"] == "https://example.com/apply"
    assert job["source_url"] == "https://example.com/job/123"


def test_dedupe_removes_same_job_across_provider_results():
    first = _normalize_apify_job({
        "id": "indeed:123", "source": "Indeed", "title": "Product Manager",
        "company": "Example Co", "location": "India",
        "applyUrl": "https://example.com/job/123",
    })
    duplicate = dict(first, provider="Jooble", provider_job_id="jooble:456")

    assert len(_dedupe([first, duplicate])) == 1
