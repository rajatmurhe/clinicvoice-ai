import re

BLOCKED_PATTERNS_INPUT = [
    r"diagnos", r"prescri", r"medication", r"dose", r"dosage",
    r"how much .* (take|dose)", r"is it (cancer|serious|an emergency)",
    r"chest pain", r"cant breathe", r"symptoms of", r"what disease",
    r"am i dying", r"nhs number", r"date of birth", r"social security",
    r"verify your identity",
]

INPUT_REGEX = re.compile("|".join(BLOCKED_PATTERNS_INPUT), re.IGNORECASE)


def check_input_safety(query):
    return bool(INPUT_REGEX.search(query))


BLOCKED_RESPONSE = "I am not able to answer clinical or medical questions like that. Please contact the clinic directly or, if this is an emergency, call your local emergency number."
