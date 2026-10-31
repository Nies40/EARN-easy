"""Paystack API integration (transaction initialization + verification).

In production, set PAYSTACK_SECRET_KEY and PAYSTACK_PUBLIC_KEY.
"""

import httpx

from app.core.config import Settings


class PaystackError(Exception):
    pass


class PaystackClient:
    BASE_URL = "https://api.paystack.co"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.paystack_secret_key)

    async def initialize(self, email: str, amount_ksh: float, reference: str) -> dict:
        if not self.is_configured:
            raise PaystackError("Paystack is not configured.")
        amount_pesewas = int(amount_ksh * 100)  # Paystack expects kobo/pesewas
        payload = {
            "email": email,
            "amount": amount_pesewas,
            "reference": reference,
            "callback_url": self.settings.paystack_callback_url or "https://example.com/callback",
            "currency": "KES",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.BASE_URL}/transaction/initialize",
                json=payload,
            headers={"Authorization": f"Bearer {self.settings.paystack_secret_key}"},
            )
            data = resp.json()
            if not data.get("status"):
                raise PaystackError(data.get("message", "Paystack init failed."))
            return data["data"]

    async def verify(self, reference: str) -> dict:
        if not self.is_configured:
            raise PaystackError("Paystack is not configured.")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.BASE_URL}/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {self.settings.paystack_secret_key}"},
            )
            data = resp.json()
            if not data.get("status"):
                raise PaystackError(data.get("message", "Verification failed."))
            return data["data"]


class MockPaystackClient:
    async def initialize(self, email: str, amount_ksh: float, reference: str) -> dict:
        return {
            "authorization_url": "https://mock.paystack.co/checkout/mock",
            "access_code": "MOCK-ACCESS-001",
            "reference": reference,
        }

    async def verify(self, reference: str) -> dict:
        return {"status": "success", "amount": 0, "reference": reference}

    @property
    def is_configured(self) -> bool:
        return True


def get_paystack_client(settings: Settings) -> PaystackClient | MockPaystackClient:
    if settings.paystack_secret_key:
        return PaystackClient(settings)
    return MockPaystackClient()