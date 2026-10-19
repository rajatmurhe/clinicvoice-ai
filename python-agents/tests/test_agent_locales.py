import pytest

from agents import escalation_agent, insurance_agent, refill_agent, intake_agent


@pytest.mark.parametrize(("language", "contains"), [("hi", "अपना नाम"), ("mr", "तुमचे नाव")])
def test_refill_initial_prompt_is_localized(language, contains):
    session = {"language": language}
    result = refill_agent.handle_refill("", session)
    assert contains in result["response"]


@pytest.mark.parametrize(("language", "contains"), [("hi", "यह बीमा प्रदाता"), ("mr", "हा विमा प्रदाता")])
def test_insurance_uncertain_provider_is_localized(language, contains):
    result = insurance_agent.handle_insurance("Some unknown provider", {"language": language})
    assert contains in result["response"]


@pytest.mark.parametrize(("language", "contains"), [("hi", "व्यक्तिगत सहायता"), ("mr", "वैयक्तिक मदत")])
def test_escalation_is_localized(language, contains):
    result = escalation_agent.handle_escalation("help", {"language": language})
    assert contains in result["response"]


@pytest.mark.parametrize(("language", "contains"), [("hi", "चिकित्सक"), ("mr", "डॉक्टरांपर्यंत")])
def test_intake_initial_prompt_is_localized(language, contains):
    result = intake_agent.handle_intake("", {"language": language})
    assert contains in result["response"]
