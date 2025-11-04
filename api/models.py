from typing import List, Optional
from typing_extensions import TypedDict


class EmailMessage(TypedDict):
    id: str
    from_: str
    to: List[str]
    subject: str
    content: str  # text/plain (ưu tiên) để preview
    date: str


class PageResult(TypedDict):
    items: List[EmailMessage]
    next_page_token: Optional[str]
    total: Optional[int]  # Tổng số email sau khi filter

