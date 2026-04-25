"""加密模組 — 負責主密碼衍生與 API Key 加解密。

使用 PBKDF2-HMAC-SHA256 從主密碼衍生 Fernet 金鑰，
所有加密/解密操作皆在本地完成。
"""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# OWASP 2023 建議的 PBKDF2-SHA256 最低迭代次數
_PBKDF2_ITERATIONS = 480_000

# Salt 長度（位元組）
_SALT_LENGTH = 16


class CryptoError(Exception):
    """加密相關錯誤的基礎例外。"""


class WrongPasswordError(CryptoError):
    """主密碼錯誤。"""


class CryptoEngine:
    """加密引擎：負責主密碼衍生與 API Key 加解密。

    使用流程：
        1. 首次初始化時呼叫 generate_salt() 生成隨機 salt
        2. 將 salt 存至 Firestore
        3. 使用主密碼 + salt 建立 CryptoEngine 實例
        4. 呼叫 encrypt() / decrypt() 處理 API Key
    """

    def __init__(self, master_password: str, salt: bytes) -> None:
        """從主密碼與 salt 衍生 Fernet 金鑰。

        Args:
            master_password: 使用者的主密碼。
            salt: 隨機 salt（16 位元組）。
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=_PBKDF2_ITERATIONS,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_password.encode("utf-8")))
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """加密明文，回傳 base64 密文字串。

        Args:
            plaintext: 要加密的 API Key 明文。

        Returns:
            Fernet 加密後的 base64 字串。
        """
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """解密密文，回傳明文。

        Args:
            ciphertext: Fernet 加密的 base64 字串。

        Returns:
            解密後的 API Key 明文。

        Raises:
            WrongPasswordError: 主密碼錯誤或密文損壞。
        """
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise WrongPasswordError("主密碼錯誤或密文已損壞") from exc

    @staticmethod
    def generate_salt() -> bytes:
        """生成密碼學安全的隨機 salt。

        Returns:
            16 位元組的隨機 bytes。
        """
        return os.urandom(_SALT_LENGTH)

    @staticmethod
    def salt_to_str(salt: bytes) -> str:
        """將 salt bytes 編碼為可儲存的 base64 字串。"""
        return base64.urlsafe_b64encode(salt).decode("utf-8")

    @staticmethod
    def salt_from_str(salt_str: str) -> bytes:
        """從 base64 字串還原 salt bytes。"""
        return base64.urlsafe_b64decode(salt_str.encode("utf-8"))
