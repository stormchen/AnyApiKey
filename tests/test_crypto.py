"""加密模組單元測試。"""

from anyapikey.crypto import CryptoEngine, WrongPasswordError
import pytest


class TestCryptoEngine:
    """CryptoEngine 測試。"""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """加密後解密應回傳原始明文。"""
        salt = CryptoEngine.generate_salt()
        engine = CryptoEngine("test-password-123", salt)

        plaintext = "sk-proj-abc123def456"
        ciphertext = engine.encrypt(plaintext)

        assert ciphertext != plaintext
        assert engine.decrypt(ciphertext) == plaintext

    def test_wrong_password_raises(self) -> None:
        """使用錯誤密碼解密應拋出 WrongPasswordError。"""
        salt = CryptoEngine.generate_salt()
        engine1 = CryptoEngine("correct-password", salt)
        engine2 = CryptoEngine("wrong-password", salt)

        ciphertext = engine1.encrypt("sk-secret-key")

        with pytest.raises(WrongPasswordError):
            engine2.decrypt(ciphertext)

    def test_different_salt_different_result(self) -> None:
        """不同 salt 應產生不同密文。"""
        salt1 = CryptoEngine.generate_salt()
        salt2 = CryptoEngine.generate_salt()
        password = "same-password"

        engine1 = CryptoEngine(password, salt1)
        engine2 = CryptoEngine(password, salt2)

        plaintext = "sk-test-key"
        cipher1 = engine1.encrypt(plaintext)
        cipher2 = engine2.encrypt(plaintext)

        # 密文不同（因為 Fernet 包含時間戳記與隨機 IV，所以即使同引擎也不同）
        # 但關鍵是跨引擎不能互相解密
        with pytest.raises(WrongPasswordError):
            engine2.decrypt(cipher1)

    def test_salt_serialization(self) -> None:
        """Salt 序列化與反序列化應保持一致。"""
        original = CryptoEngine.generate_salt()
        encoded = CryptoEngine.salt_to_str(original)
        decoded = CryptoEngine.salt_from_str(encoded)

        assert original == decoded

    def test_generate_salt_uniqueness(self) -> None:
        """每次生成的 salt 應該不同。"""
        salts = {CryptoEngine.generate_salt() for _ in range(100)}
        assert len(salts) == 100

    def test_generate_salt_length(self) -> None:
        """Salt 長度應為 16 位元組。"""
        salt = CryptoEngine.generate_salt()
        assert len(salt) == 16

    def test_empty_plaintext(self) -> None:
        """空字串也能正確加密解密。"""
        salt = CryptoEngine.generate_salt()
        engine = CryptoEngine("password", salt)

        ciphertext = engine.encrypt("")
        assert engine.decrypt(ciphertext) == ""

    def test_unicode_plaintext(self) -> None:
        """中文與特殊字元也能正確處理。"""
        salt = CryptoEngine.generate_salt()
        engine = CryptoEngine("密碼", salt)

        plaintext = "這是一把包含特殊字元的 Key：sk-🔑-中文"
        ciphertext = engine.encrypt(plaintext)
        assert engine.decrypt(ciphertext) == plaintext
