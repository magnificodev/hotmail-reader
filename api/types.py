from typing import List, Optional, TypedDict


class EmailMessage(TypedDict):
    id: str
    from_: str
    to: List[str]
    subject: str
    snippet: str
    date: str


class PageResult(TypedDict):
    items: List[EmailMessage]
    next_page_token: Optional[str]

