from app.services.phone import normalize_phone


def test_moroccan_phone_normalization():
    assert normalize_phone('06 12 34 56 78', 'MA') == '+212612345678'
    assert normalize_phone('+212612345678', 'MA') == '+212612345678'
