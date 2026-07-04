"""Firestore 儲存模組 — 負責與雲端溝通。

封裝所有 Firestore 操作，包括 API Key 的 CRUD
以及加密元資料（salt）的管理。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from google.cloud.firestore_v1.client import Client as FirestoreClient

from anyapikey.crypto import CryptoEngine
from anyapikey.models import KeyEntry

# Firestore 集合名稱
_KEYS_COLLECTION = "api_keys"
_META_COLLECTION = "_meta"
_CRYPTO_DOC = "crypto"


class StoreError(Exception):
    """儲存相關錯誤。"""


class KeyStore:
    """Firestore API Key 儲存庫。

    所有與 Firestore 的通訊都透過此類別完成，
    包括 salt 元資料與加密 Key 的 CRUD 操作。
    """

    def __init__(self, credentials_path: str | Path) -> None:
        """使用 Service Account JSON 初始化 Firestore 連線。

        Args:
            credentials_path: Service Account JSON 檔案路徑。

        Raises:
            StoreError: 憑證檔案不存在或連線失敗。
        """
        path = Path(credentials_path).expanduser()
        if not path.exists():
            raise StoreError(
                f"找不到 Firestore 憑證檔案：{path}\n"
                "請將 Service Account JSON 放到上述路徑，或執行 'anyapikey config' 修改路徑。"
            )
        try:
            self._db = FirestoreClient.from_service_account_json(str(path))
            # 預先驗證憑證，避免 gRPC 因為認證錯誤而無限重試掛起
            if self._db._credentials:
                from google.auth.transport.requests import Request
                self._db._credentials.refresh(Request())
        except Exception as exc:
            raise StoreError(f"Firestore 連線失敗：{exc}") from exc

        self._keys = self._db.collection(_KEYS_COLLECTION)
        self._meta = self._db.collection(_META_COLLECTION)

    # --- 元資料操作 ---

    def get_salt(self) -> bytes | None:
        """取得儲存在 Firestore 的 PBKDF2 salt。

        Returns:
            salt bytes，首次使用時回傳 None。
        """
        doc = self._meta.document(_CRYPTO_DOC).get()
        if doc.exists:
            salt_str = doc.to_dict().get("salt")
            if salt_str:
                return CryptoEngine.salt_from_str(salt_str)
        return None

    def save_salt(self, salt: bytes) -> None:
        """儲存 salt 至 Firestore。

        Args:
            salt: 隨機生成的 PBKDF2 salt。
        """
        self._meta.document(_CRYPTO_DOC).set({
            "salt": CryptoEngine.salt_to_str(salt),
            "created_at": datetime.now(timezone.utc),
        })

    def test_connection(self) -> bool:
        """測試 Firestore 連線是否正常。

        Returns:
            True 表示連線成功。

        Raises:
            StoreError: 連線失敗。
        """
        try:
            # 嘗試讀取 _meta 集合（即使文件不存在也不會報錯），並設定較短的逾時時間避免掛起
            self._meta.document(_CRYPTO_DOC).get(timeout=10.0)
            return True
        except Exception as exc:
            raise StoreError(f"Firestore 連線測試失敗：{exc}") from exc

    # --- Key CRUD ---

    def save(
        self,
        service: str,
        encrypted_key: str,
        category: str = "",
        note: str = "",
    ) -> None:
        """儲存或更新一筆加密 API Key。

        Args:
            service: 服務名稱。
            encrypted_key: 加密後的密文。
            category: 分類標籤。
            note: 備註說明。
        """
        now = datetime.now(timezone.utc)
        doc_ref = self._keys.document(service)
        existing = doc_ref.get()

        entry = KeyEntry(
            service=service,
            encrypted_key=encrypted_key,
            category=category,
            note=note,
            created_at=existing.to_dict().get("created_at", now)
            if existing.exists
            else now,
            updated_at=now,
        )
        doc_ref.set(entry.to_dict())

    def get(self, service: str) -> KeyEntry | None:
        """取得單筆 Key 條目。

        Args:
            service: 服務名稱。

        Returns:
            KeyEntry 實例，不存在時回傳 None。
        """
        doc = self._keys.document(service).get()
        if doc.exists:
            return KeyEntry.from_dict(service, doc.to_dict())
        return None

    def list_all(self, category: str | None = None) -> list[KeyEntry]:
        """列出所有 Key 條目。

        Args:
            category: 篩選分類（None 表示全部）。

        Returns:
            KeyEntry 列表（不含明文金鑰）。
        """
        if category:
            query = self._keys.where("category", "==", category)
            docs = query.stream()
        else:
            docs = self._keys.stream()

        entries = []
        for doc in docs:
            entries.append(KeyEntry.from_dict(doc.id, doc.to_dict()))
        return entries

    def delete(self, service: str) -> bool:
        """刪除一筆 Key。

        Args:
            service: 服務名稱。

        Returns:
            True 表示成功刪除，False 表示服務不存在。
        """
        doc_ref = self._keys.document(service)
        if not doc_ref.get().exists:
            return False
        doc_ref.delete()
        return True

    def exists(self, service: str) -> bool:
        """檢查服務名稱是否已存在。

        Args:
            service: 服務名稱。

        Returns:
            True 表示已存在。
        """
        return self._keys.document(service).get().exists

    def rename(self, old_name: str, new_name: str) -> bool:
        """重新命名服務名稱。

        讀取舊文件 → 寫入新文件 → 刪除舊文件。

        Args:
            old_name: 原服務名稱。
            new_name: 新服務名稱。

        Returns:
            True 表示成功。

        Raises:
            StoreError: 舊名稱不存在或新名稱已存在。
        """
        if not self.exists(old_name):
            raise StoreError(f"服務 '{old_name}' 不存在")
        if self.exists(new_name):
            raise StoreError(f"服務 '{new_name}' 已存在")

        old_doc = self._keys.document(old_name).get()
        data = old_doc.to_dict()
        data["updated_at"] = datetime.now(timezone.utc)
        self._keys.document(new_name).set(data)
        self._keys.document(old_name).delete()
        return True
