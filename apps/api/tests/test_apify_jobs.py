from app.services.apify_jobs import _experience_matches, _parse_experience_text, _title_matches

def test_title_matching():
    assert _title_matches("Senior Product Manager", "Product Manager")
    assert _title_matches("Program Manager - AI", "AI Program Manager")
    assert _title_matches("AI Technical Program Manager", "AI Program Manager")
    assert not _title_matches("Product Marketing Manager", "Product Manager")
    assert not _title_matches("AI Product Manager", "AI Program Manager")

def test_experience():
    assert _experience_matches(3, 8, 5)
    assert not _experience_matches(6, 10, 5)

def test_parse_experience():
    assert _parse_experience_text("5-10 Yrs") == (5.0, 10.0)
    assert _parse_experience_text("8+ years") == (8.0, None)
