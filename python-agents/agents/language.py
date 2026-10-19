"""Small deterministic language helpers for non-generative agent replies."""


def localized(session, english, hindi, marathi):
    language = (session or {}).get("language", "en")
    return {"hi": hindi, "mr": marathi}.get(language, english)
