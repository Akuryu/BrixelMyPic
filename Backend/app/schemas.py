
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any


class PaymentConfirmRequest(BaseModel):
    code: str = Field(..., min_length=4)


class RedeemRequest(BaseModel):
    token: str = Field(..., min_length=4)


class PreparePackageResponse(BaseModel):
    code: str
    status: str = "pending"


class ConfirmPaymentResponse(BaseModel):
    redeem_token: str
    status: str = "paid"


class Metadata(BaseModel):
    public_code: str
    redeem_token: str | None = None
    status: str
    params: dict[str, Any]
    width: int
    height: int
    piece_type: str
    palette_size: int
    created_at: float
    files: dict[str, str] = {}
