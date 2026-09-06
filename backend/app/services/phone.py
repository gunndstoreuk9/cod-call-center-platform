import re


def normalize_phone(raw: str, country: str = "MA") -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Phone is required")
    has_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 8:
        raise ValueError("Phone number is too short")

    country = (country or "MA").upper()
    if country == "MA":
        if digits.startswith("212"):
            return "+" + digits
        if digits.startswith("0"):
            return "+212" + digits[1:]
        if len(digits) == 9:
            return "+212" + digits
    return ("+" if has_plus else "+") + digits
