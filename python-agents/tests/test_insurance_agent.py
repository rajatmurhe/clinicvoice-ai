from agents.insurance_agent import handle_insurance, check_provider


def test_accepted_providers():
    r = handle_insurance("Do you accept Aetna?", {})
    assert "Yes, we accept Aetna" in r["response"]
    assert r["agent"] == "insurance"


def test_spacing_tolerant_matching():
    # Regression: "UnitedHealthcare" used to miss "united healthcare".
    assert check_provider("Do you accept UnitedHealthcare?") == "united healthcare"
    assert check_provider("is  bluecross blueshield  ok") == "blue cross blue shield"


def test_unknown_provider():
    r = handle_insurance("Do you accept Max Bupa?", {})
    assert "do not have that specific provider confirmed" in r["response"]
