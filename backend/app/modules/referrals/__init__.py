from urllib.parse import quote

def referral_link(username: str, referral_code: str) -> str:
    return (
        f"https://your-site.example/{quote(username)}"
        f"?ref={quote(referral_code)}"
    )