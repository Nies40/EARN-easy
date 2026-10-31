"""Safaricom Daraja M-Pesa API integration (STK push + B2C).

Uses httpx for HTTP calls. In production, set MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET,
MPESA_PASSKEY, MPESA_SHORTCODE, and MPESA_CALLBACK_URL in the environment.
In sandbox, the base URL is https://sandbox.safaricom.co.ke.
"""

import base64
from datetime import datetime

import httpx

from app.core.config import Settings


class MpesaError(Exception):
    pass


class MpesaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = (
            "https://api.safaricom.co.ke"
            if settings.mpesa_environment == "production"
            else "https://sandbox.safaricom.co.ke"
        )
        self._token: str | None = None

    @property
    def is_configured(self) -> bool:
        return all(
            (
                self.settings.mpesa_consumer_key,
                self.settings.mpesa_consumer_secret,
                self.settings.mpesa_passkey,
                self.settings.mpesa_shortcode,
            )
        )

    async def _get_access_token(self) -> str:
        if self._token:
            return self._token
        if not self.is_configured:
            raise MpesaError("M-Pesa is not configured. Set MPESA_* environment variables.")
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url,
                auth=(
                    self.settings.mpesa_consumer_key,
                    self.settings.mpesa_consumer_secret,
                ),
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
            return self._token

    async def stk_push(self, phone: str, amount: float, account_reference: str) -> dict:
        """Trigger an STK push to the user's phone for the given amount."""
        if not self.is_configured:
            raise MpesaError("M-Pesa is not configured.")
        token = await self._get_access_token()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(
            f"{self.settings.mpesa_shortcode}{self.settings.mpesa_passkey}{timestamp}".encode()
        ).decode()
        payload = {
            "BusinessShortCode": self.settings.mpesa_shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": self.settings.mpesa_shortcode,
            "PhoneNumber": phone,
            "CallBackURL": self.settings.mpesa_callback_url or "https://example.com/callback",
            "AccountReference": account_reference[:12],
            "TransactionDesc": "Easyearn wallet deposit",
        }
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
            data = resp.json()
            if resp.status_code != 200:
                raise MpesaError(data.get("errorMessage", "STK push failed."))
            return data


class MockMpesaClient:
    """Stub used when M-Pesa is not configured — simulates a successful STK push."""

    async def stk_push(self, phone: str, amount: float, account_reference: str) -> dict:
        return {
            "MerchantRequestID": "MOCK-REQ-001",
            "CheckoutRequestID": "MOCK-CHECKOUT-001",
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing (mock)",
            "CustomerMessage": "Success. Request accepted for processing (mock)",
        }

    @property
    def is_configured(self) -> bool:
        return True


def get_mpesa_client(settings: Settings) -> MpesaClient | MockMpesaClient:
    if all(
        (
            settings.mpesa_consumer_key,
            settings.mpesa_consumer_secret,
            settings.mpesa_passkey,
            settings.mpesa_shortcode,
        )
    ):
        return MpesaClient(settings)
    return MockMpesaClient()