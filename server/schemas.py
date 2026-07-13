"""Request bodies for the JSON endpoints."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str


class TryOnProduct(BaseModel):
    id: str | None = None
    name: str | None = None
    image_url: str


class TryOnRequest(BaseModel):
    session_id: str
    products: list[TryOnProduct]


class CartAddRequest(BaseModel):
    session_id: str
    product_id: str
    name: str
    category: str = ""
    price: int = 0
    quantity: int = 1
    image_url: str = ""


class CartRemoveRequest(BaseModel):
    session_id: str
    product_id: str


class CartUpdateRequest(BaseModel):
    session_id: str
    product_id: str
    quantity: int


class CheckoutDetailsRequest(BaseModel):
    session_id: str
    name: str = ""
    phone: str = ""
    address: str = ""
    city: str = ""
    date: str = ""
    instructions: str = ""


class TrackOrderRequest(BaseModel):
    order_number: str
