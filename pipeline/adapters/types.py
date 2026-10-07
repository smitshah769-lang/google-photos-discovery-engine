from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CollectedItem:
    """Normalized adapter output stored in RawRecord.payload_json."""

    native_id: str
    source: str
    text: str
    authored_at: str | None
    source_url: str | None
    locale: str | None = None
    title: str | None = None
    thread_context: str | None = None
    raw_api_payload: dict[str, Any] | None = None
    developer_reply: str | None = None
    has_user_text: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "adapter_version": 1,
            "native_id": self.native_id,
            "source": self.source,
            "text": self.text,
            "title": self.title,
            "authored_at": self.authored_at,
            "source_url": self.source_url,
            "locale": self.locale,
            "thread_context": self.thread_context,
            "developer_reply": self.developer_reply,
            "has_user_text": self.has_user_text,
            "raw_api_payload": self.raw_api_payload,
        }


@dataclass
class AdapterReceipt:
    status: str  # success | partial | failed | gap
    item_count: int
    notes: str
    coverage_limits: list[str] = field(default_factory=list)


@dataclass
class AdapterResult:
    items: list[CollectedItem]
    receipt: AdapterReceipt
