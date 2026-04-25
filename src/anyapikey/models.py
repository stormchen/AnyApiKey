"""資料模型定義。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class KeyEntry:
    """代表一筆 API Key 條目。

    Attributes:
        service: 服務名稱（如 OpenAI, Anthropic）。
        encrypted_key: Fernet 加密後的密文字串。
        category: 分類標籤（如 AI, Cloud, Payment）。
        note: 備註說明。
        created_at: 建立時間。
        updated_at: 最後更新時間。
    """

    service: str
    encrypted_key: str
    category: str = ""
    note: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """轉換為 Firestore 文件格式的字典。"""
        return {
            "encrypted_key": self.encrypted_key,
            "category": self.category,
            "note": self.note,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, service: str, data: dict) -> KeyEntry:
        """從 Firestore 文件字典建立 KeyEntry 實例。"""
        return cls(
            service=service,
            encrypted_key=data.get("encrypted_key", ""),
            category=data.get("category", ""),
            note=data.get("note", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc)),
            updated_at=data.get("updated_at", datetime.now(timezone.utc)),
        )
