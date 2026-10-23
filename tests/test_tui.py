"""TUI 模組測試 — 使用 Textual Pilot 與記憶體 FakeStore。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

import anyapikey.crypto as crypto_mod
from anyapikey.config import Config
from anyapikey.crypto import CryptoEngine
from anyapikey.models import KeyEntry
from anyapikey.store import StoreError

pytest.importorskip("textual")

from textual.widgets import DataTable, Input, Label  # noqa: E402

from anyapikey import tui  # noqa: E402


class FakeStore:
    """測試用的記憶體 KeyStore,介面與 KeyStore 相同。"""

    def __init__(self) -> None:
        self.salt = CryptoEngine.generate_salt()
        self.entries: dict[str, KeyEntry] = {}

    def get_salt(self) -> bytes:
        return self.salt

    def list_all(self, category: str | None = None) -> list[KeyEntry]:
        items = sorted(self.entries.values(), key=lambda e: e.service.lower())
        if category:
            items = [e for e in items if e.category == category]
        return items

    def get(self, service: str) -> KeyEntry | None:
        return self.entries.get(service)

    def exists(self, service: str) -> bool:
        return service in self.entries

    def save(
        self, service: str, encrypted_key: str, category: str = "", note: str = ""
    ) -> None:
        now = datetime.now(timezone.utc)
        old = self.entries.get(service)
        self.entries[service] = KeyEntry(
            service=service,
            encrypted_key=encrypted_key,
            category=category,
            note=note,
            created_at=old.created_at if old else now,
            updated_at=now,
        )

    def delete(self, service: str) -> bool:
        return self.entries.pop(service, None) is not None

    def rename(self, old_name: str, new_name: str) -> bool:
        if old_name not in self.entries:
            raise StoreError(f"服務 '{old_name}' 不存在")
        if new_name in self.entries:
            raise StoreError(f"服務 '{new_name}' 已存在")
        self.entries[new_name] = self.entries.pop(old_name)
        self.entries[new_name].service = new_name
        return True


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試時降低 PBKDF2 迭代次數以加速。"""
    monkeypatch.setattr(crypto_mod, "_PBKDF2_ITERATIONS", 1_000)


def _make_app(
    tmp_path, monkeypatch: pytest.MonkeyPatch, idle_seconds: int | None = None
):
    if idle_seconds is not None:
        monkeypatch.setattr(tui, "IDLE_LOCK_SECONDS", idle_seconds)
    store = FakeStore()
    config = Config(config_dir=tmp_path / "cfg")
    engine = CryptoEngine("test123", store.salt)
    store.save("OpenAI", engine.encrypt("sk-test-1234567890abcd"), "AI", "GPT 測試")
    store.save("AWS", engine.encrypt("AKIA-ABCDEFGHIJKLMNOP"), "Cloud", "")
    app = tui.AnyApiKeyApp(config, store)
    return app, store


def _label_text(app, selector: str) -> str:
    return str(app.query_one(selector, Label).render())


class TestUnlockScreen:
    """解鎖畫面測試。"""

    def test_empty_password_shows_error(self, tmp_path, monkeypatch) -> None:
        app, _store = _make_app(tmp_path, monkeypatch)

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                assert isinstance(app.screen, tui.UnlockScreen)
                await pilot.click("#unlock-btn")
                await pilot.pause()
                assert "主密碼不能為空" in _label_text(app, "#unlock-err")

        asyncio.run(run())

    def test_wrong_password_stays_locked(self, tmp_path, monkeypatch) -> None:
        app, _store = _make_app(tmp_path, monkeypatch)

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#pw", Input).value = "wrong-password"
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(app.screen, tui.UnlockScreen)
                assert "主密碼錯誤" in _label_text(app, "#unlock-err")

        asyncio.run(run())

    def test_correct_password_unlocks(self, tmp_path, monkeypatch) -> None:
        app, _store = _make_app(tmp_path, monkeypatch)

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#pw", Input).value = "test123"
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(app.screen, tui.MainScreen)

        asyncio.run(run())


class TestMainScreen:
    """主畫面測試。"""

    def test_table_shows_all_entries(self, tmp_path, monkeypatch) -> None:
        app, _store = _make_app(tmp_path, monkeypatch)

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#pw", Input).value = "test123"
                await pilot.press("enter")
                await pilot.pause()
                table = app.query_one("#keys-table", DataTable)
                assert table.row_count == 2

        asyncio.run(run())

    def test_detail_shows_masked_key(self, tmp_path, monkeypatch) -> None:
        app, _store = _make_app(tmp_path, monkeypatch)

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#pw", Input).value = "test123"
                await pilot.press("enter")
                await pilot.pause()
                # 排序後第一列是 AWS
                assert _label_text(app, "#d-name") == "AWS"
                masked = _label_text(app, "#d-key")
                assert "•" in masked
                assert "AKIA-ABCDEFGHIJKLMNOP" not in masked

        asyncio.run(run())

    def test_copy_sends_to_clipboard(self, tmp_path, monkeypatch) -> None:
        app, _store = _make_app(tmp_path, monkeypatch)
        calls: list[tuple[str, int]] = []
        monkeypatch.setattr(
            tui, "copy_to_clipboard", lambda text, ttl=30: calls.append((text, ttl)),
        )

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#pw", Input).value = "test123"
                await pilot.press("enter")
                await pilot.pause()
                await pilot.press("enter")  # RowSelected → 複製
                await pilot.pause()
                assert calls == [("AKIA-ABCDEFGHIJKLMNOP", 30)]

        asyncio.run(run())


class TestModals:
    """對話框流程測試。"""

    def test_add_key_flow(self, tmp_path, monkeypatch) -> None:
        app, store = _make_app(tmp_path, monkeypatch)

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#pw", Input).value = "test123"
                await pilot.press("enter")
                await pilot.pause()

                await pilot.press("n")
                await pilot.pause()
                assert isinstance(app.screen, tui.AddKeyModal)
                app.query_one("#add-service", Input).value = "Stripe"
                app.query_one("#add-key", Input).value = "sk-live-new-key"
                app.query_one("#add-category", Input).value = "Payment"
                await pilot.click("#m-save")
                await pilot.pause()
                await pilot.pause()

                assert "Stripe" in store.entries
                table = app.query_one("#keys-table", DataTable)
                assert table.row_count == 3

        asyncio.run(run())

    def test_add_duplicate_shows_error(self, tmp_path, monkeypatch) -> None:
        app, store = _make_app(tmp_path, monkeypatch)

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#pw", Input).value = "test123"
                await pilot.press("enter")
                await pilot.pause()

                await pilot.press("n")
                await pilot.pause()
                app.query_one("#add-service", Input).value = "OpenAI"
                app.query_one("#add-key", Input).value = "sk-x"
                await pilot.click("#m-save")
                await pilot.pause()

                assert isinstance(app.screen, tui.AddKeyModal)
                assert "已存在" in _label_text(app, "#m-err")
                assert len(store.entries) == 2

        asyncio.run(run())

    def test_delete_flow(self, tmp_path, monkeypatch) -> None:
        app, store = _make_app(tmp_path, monkeypatch)

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#pw", Input).value = "test123"
                await pilot.press("enter")
                await pilot.pause()

                await pilot.press("d")
                await pilot.pause()
                assert isinstance(app.screen, tui.DeleteConfirmModal)
                await pilot.click("#m-ok")
                await pilot.pause()
                await pilot.pause()

                assert "AWS" not in store.entries
                table = app.query_one("#keys-table", DataTable)
                assert table.row_count == 1

        asyncio.run(run())

    def test_rename_flow(self, tmp_path, monkeypatch) -> None:
        app, store = _make_app(tmp_path, monkeypatch)

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#pw", Input).value = "test123"
                await pilot.press("enter")
                await pilot.pause()

                await pilot.press("r")
                await pilot.pause()
                assert isinstance(app.screen, tui.RenameModal)
                app.query_one("#rename-input", Input).value = "aws-production"
                await pilot.click("#m-save")
                await pilot.pause()
                await pilot.pause()

                assert "aws-production" in store.entries
                assert "AWS" not in store.entries

        asyncio.run(run())


class TestAutoLock:
    """閒置自動鎖定測試。"""

    def test_idle_timeout_relocks(self, tmp_path, monkeypatch) -> None:
        app, _store = _make_app(tmp_path, monkeypatch, idle_seconds=2)

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#pw", Input).value = "test123"
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(app.screen, tui.MainScreen)

                await pilot.pause(3.5)
                assert isinstance(app.screen, tui.UnlockScreen)

        asyncio.run(run())

    def test_manual_lock_returns_to_unlock(self, tmp_path, monkeypatch) -> None:
        app, _store = _make_app(tmp_path, monkeypatch)

        async def run() -> None:
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one("#pw", Input).value = "test123"
                await pilot.press("enter")
                await pilot.pause()

                await pilot.press("l")
                await pilot.pause()
                assert isinstance(app.screen, tui.UnlockScreen)

        asyncio.run(run())


def test_mask_key() -> None:
    """遮罩函式應保留前綴與後綴,隱藏中段。"""
    assert tui.mask_key("sk-proj-1234567890abcdef") == "sk-proj-" + "•" * 8 + "cdef"
    assert tui.mask_key("short") == "s••••t"
    assert tui.mask_key("") == "•" * 4
