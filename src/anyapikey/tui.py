"""TUI 模組 — Textual 互動介面(側欄式版面)。

與 CLI 共用 Config / KeyStore / CryptoEngine,所有加解密
與雲端操作皆與命令列版本完全一致;額外提供閒置自動鎖定、
限時明文顯示等 UI 專屬的安全強化。
"""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.dom import DOMNode
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Input, Label, Static

from anyapikey.clipboard import copy_to_clipboard
from anyapikey.config import Config
from anyapikey.crypto import CryptoEngine, WrongPasswordError
from anyapikey.models import KeyEntry
from anyapikey.store import KeyStore

# 閒置多久後自動鎖定(秒)
IDLE_LOCK_SECONDS = 300

# 明文顯示多久後自動重新遮罩(秒)
REVEAL_SECONDS = 5


def mask_key(key: str) -> str:
    """將 API Key 遮罩為「前綴 + •••• + 後綴」形式。"""
    if len(key) > 16:
        return f"{key[:8]}{'•' * 8}{key[-4:]}"
    if len(key) > 1:
        return f"{key[0]}{'•' * max(4, len(key) - 2)}{key[-1]}"
    return "•" * 4


_CSS = """
UnlockScreen {
    align: center middle;
}
#unlock-box {
    width: 64;
    height: auto;
    padding: 1 2;
    background: $panel;
    border: round $border;
}
#unlock-title { text-style: bold; color: $accent; }
#unlock-sub { color: $text-muted; margin-bottom: 1; }
#unlock-btn { margin-top: 1; }
#unlock-err { color: $error; margin-top: 1; }
#unlock-note { color: $text-disabled; margin-top: 1; }

MainScreen { layout: vertical; }

#topbar {
    dock: top;
    height: 3;
    background: $panel;
    border-bottom: solid $border;
    padding: 0 1;
    align: left middle;
}
#logo { width: auto; text-style: bold; color: $accent; }
#sync { width: auto; color: $success; margin-left: 2; }
#topbar-spacer { width: 1fr; }
#locktimer { width: auto; color: $text-muted; }
#lock-btn { width: auto; margin-left: 1; }

#body { height: 1fr; }
#sidebar {
    width: 28;
    background: $panel;
    border-right: solid $border;
    padding: 1;
}
#side-title { color: $text-muted; text-style: bold; margin-bottom: 1; }
#cats { height: 1fr; }
.cat-btn {
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    color: $text;
    min-width: 0;
}
.cat-btn.current { background: $accent; color: $background; text-style: bold; }
#add-btn { margin-top: 1; width: 100%; }

#maincol { padding: 0 1 1 0; }
#keys-table {
    height: 1fr;
    background: $panel;
    border: solid $border;
}
#detail {
    height: 5;
    margin-top: 1;
    background: $panel;
    border: solid $border;
    padding: 0 1;
    align: left middle;
}
#d-name { width: auto; text-style: bold; }
#d-key { width: 1fr; color: $text-muted; margin-left: 1; }
#d-actions { width: auto; }
#d-actions Button { margin-left: 1; }

AddKeyModal, RenameModal, DeleteConfirmModal {
    align: center middle;
    background: black 55%;
}
#dialog {
    width: 64;
    height: auto;
    padding: 1 2;
    background: $panel;
    border: round $border;
}
#m-title { text-style: bold; margin-bottom: 1; }
#m-text { color: $text; margin-bottom: 1; }
#dialog Input { margin-bottom: 1; }
#m-err { color: $error; }
#m-actions { height: auto; align: right middle; margin-top: 1; }
#m-actions Button { margin-left: 1; }
"""


class UnlockScreen(Screen[None]):
    """主密碼解鎖畫面。"""

    def __init__(self, config: Config, store: KeyStore) -> None:
        super().__init__()
        self._config = config
        self._store = store

    def compose(self) -> ComposeResult:
        with Vertical(id="unlock-box"):
            yield Label("🔐 AnyApiKey", id="unlock-title")
            yield Label("請輸入主密碼以解鎖保險庫", id="unlock-sub")
            yield Input(password=True, placeholder="🔑 主密碼", id="pw")
            yield Button("解鎖", id="unlock-btn", variant="primary")
            yield Label("", id="unlock-err")
            yield Label(
                "密碼僅用於本地 PBKDF2 衍生金鑰,不會被儲存或上傳。",
                id="unlock-note",
            )

    def on_mount(self) -> None:
        self.query_one("#pw", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "pw":
            self._unlock()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "unlock-btn":
            self._unlock()

    def _unlock(self) -> None:
        password = self.query_one("#pw", Input).value
        if not password:
            self._set_err("主密碼不能為空")
            return

        try:
            salt = self._store.get_salt()
            entries = self._store.list_all()
        except Exception as exc:
            self._set_err(f"無法連線 Firestore:{exc}")
            return

        if salt is None:
            self._set_err("尚未初始化,請先執行 'anyapikey init'")
            return

        engine = CryptoEngine(password, salt)
        if entries:
            # 用第一筆 Key 驗證密碼正確性(與 CLI verify 相同邏輯)
            try:
                engine.decrypt(entries[0].encrypted_key)
            except WrongPasswordError:
                self._set_err("主密碼錯誤")
                return

        self.app.switch_screen(
            MainScreen(self._config, self._store, engine, entries)
        )

    def _set_err(self, message: str) -> None:
        self.query_one("#unlock-err", Label).update(f"❌ {message}")


class AddKeyModal(ModalScreen[dict | None]):
    """新增 API Key 表單。"""

    BINDINGS = [Binding("escape", "cancel", "取消", show=False)]

    def __init__(self, existing: set[str]) -> None:
        super().__init__()
        self._existing = existing

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("💾 新增 API Key", id="m-title")
            yield Input(placeholder="服務名稱(如 OpenAI)", id="add-service")
            yield Input(placeholder="API Key", password=True, id="add-key")
            yield Input(placeholder="分類(如 AI、Cloud)", id="add-category")
            yield Input(placeholder="備註(選填)", id="add-note")
            yield Label("", id="m-err")
            with Horizontal(id="m-actions"):
                yield Button("取消", id="m-cancel")
                yield Button("🔒 加密儲存", id="m-save", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#add-service", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._save()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "m-cancel":
            self.dismiss(None)
        elif event.button.id == "m-save":
            self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        service = self.query_one("#add-service", Input).value.strip()
        key = self.query_one("#add-key", Input).value
        category = self.query_one("#add-category", Input).value.strip()
        note = self.query_one("#add-note", Input).value.strip()

        err = self.query_one("#m-err", Label)
        if not service or not key:
            err.update("❌ 服務名稱與 API Key 不能為空")
            return
        if service in self._existing:
            err.update(f"❌ 服務名稱 '{service}' 已存在")
            return

        self.dismiss(
            {"service": service, "key": key, "category": category, "note": note}
        )


class RenameModal(ModalScreen[str | None]):
    """重新命名服務表單。"""

    BINDINGS = [Binding("escape", "cancel", "取消", show=False)]

    def __init__(self, service: str, existing: set[str]) -> None:
        super().__init__()
        self._service = service
        self._existing = existing - {service}

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"✏️ 重新命名 '{self._service}'", id="m-title")
            yield Input(value=self._service, id="rename-input")
            yield Label("", id="m-err")
            with Horizontal(id="m-actions"):
                yield Button("取消", id="m-cancel")
                yield Button("確認", id="m-save", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#rename-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._save()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "m-cancel":
            self.dismiss(None)
        elif event.button.id == "m-save":
            self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        name = self.query_one("#rename-input", Input).value.strip()
        err = self.query_one("#m-err", Label)
        if not name:
            err.update("❌ 名稱不能為空")
            return
        if name in self._existing:
            err.update(f"❌ 服務名稱 '{name}' 已存在")
            return
        self.dismiss(name)


class DeleteConfirmModal(ModalScreen[bool]):
    """刪除確認對話框。"""

    BINDINGS = [Binding("escape", "cancel", "取消", show=False)]

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("🗑 刪除確認", id="m-title")
            yield Label(
                f"確定要刪除 '{self._service}' 的 API Key?此操作無法復原。",
                id="m-text",
            )
            with Horizontal(id="m-actions"):
                yield Button("取消", id="m-cancel")
                yield Button("刪除", id="m-ok", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "m-cancel":
            self.dismiss(False)
        elif event.button.id == "m-ok":
            self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class CategoryButton(Button):
    """側欄分類按鈕，攜帶對應的分類名稱。"""

    def __init__(self, label: str, category_name: str, **kwargs: Any) -> None:
        super().__init__(label, **kwargs)
        self.category_name = category_name


class MainScreen(Screen[None]):
    """主畫面:側欄分類 + Key 列表 + 操作列。"""

    BINDINGS = [
        Binding("n", "add", "新增"),
        Binding("enter", "copy", "複製"),
        Binding("r", "rename", "重新命名"),
        Binding("d", "delete", "刪除"),
        Binding("v", "reveal", "顯示"),
        Binding("l", "lock", "鎖定"),
    ]

    def __init__(
        self,
        config: Config,
        store: KeyStore,
        engine: CryptoEngine,
        entries: list[KeyEntry],
    ) -> None:
        super().__init__()
        self._config = config
        self._store = store
        self._engine = engine
        self._entries = entries
        self._cat: str | None = None
        self._cat_names: list[str] = [""]
        self._idle = IDLE_LOCK_SECONDS
        self._reveal_timer: Any = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Label("🔐 AnyApiKey", id="logo")
            yield Label("● 已同步 Firestore", id="sync")
            yield Static("", id="topbar-spacer")
            yield Label("", id="locktimer")
            yield Button("🔒 鎖定", id="lock-btn")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Label("分類", id="side-title")
                yield Vertical(id="cats")
                yield Button("＋ 新增 Key", id="add-btn")
            with Vertical(id="maincol"):
                yield DataTable(id="keys-table")
                with Horizontal(id="detail"):
                    yield Label("—", id="d-name")
                    yield Label("未選取服務", id="d-key")
                    with Horizontal(id="d-actions"):
                        yield Button("📋 複製", id="copy-btn", variant="primary")
                        yield Button("👁 顯示", id="reveal-btn")
                        yield Button("✏️ 重新命名", id="rename-btn")
                        yield Button("🗑 刪除", id="del-btn", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        table = self._table()
        table.add_columns("服務", "分類", "備註", "更新")
        table.cursor_type = "row"
        self._reload()
        self.set_interval(1.0, self._tick_idle)
        table.focus()

    # --- 版面更新 ---

    def _table(self) -> DataTable:
        return self.query_one("#keys-table", DataTable)

    def _reload(self, keep: str | None = None) -> None:
        """從 Firestore 重新載入並重繪表格與側欄。"""
        try:
            self._entries = self._store.list_all()
        except Exception as exc:
            self.notify(f"❌ 讀取 Firestore 失敗:{exc}", severity="error")
            return

        entries = sorted(self._entries, key=lambda e: e.service.lower())
        visible = [e for e in entries if not self._cat or e.category == self._cat]

        table = self._table()
        table.clear()
        for entry in visible:
            table.add_row(
                entry.service,
                entry.category or "—",
                entry.note or "—",
                entry.updated_at.strftime("%m-%d %H:%M"),
                key=entry.service,
            )

        if keep is not None:
            names = [e.service for e in visible]
            if keep in names:
                table.move_cursor(row=names.index(keep))
        elif table.row_count > 0:
            table.move_cursor(row=0)

        self._refresh_cats()
        self._refresh_detail()

    def _refresh_cats(self) -> None:
        """依目前資料重建側欄分類按鈕。"""
        counts: dict[str, int] = {}
        for entry in self._entries:
            if entry.category:
                counts[entry.category] = counts.get(entry.category, 0) + 1

        names = ["", *sorted(counts)]
        self._cat_names = names

        cats = self.query_one("#cats", Vertical)
        cats.remove_children()
        buttons = []
        for name in names:
            label = (
                f"全部 ({len(self._entries)})" if not name
                else f"{name} ({counts[name]})"
            )
            button = CategoryButton(label, category_name=name, classes="cat-btn")
            button.set_class(name == self._cat, "current")
            buttons.append(button)
        cats.mount(*buttons)

    def _current_entry(self) -> KeyEntry | None:
        """取得游標所在列的 KeyEntry。"""
        table = self._table()
        if table.row_count == 0:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return None
        for entry in self._entries:
            if entry.service == row_key.value:
                return entry
        return None

    def _refresh_detail(self) -> None:
        entry = self._current_entry()
        actions = self.query_one("#d-actions", Horizontal)
        if entry is None:
            self.query_one("#d-name", Label).update("—")
            self.query_one("#d-key", Label).update("未選取服務")
            actions.display = False
            return
        actions.display = True
        self.query_one("#d-name", Label).update(entry.service)
        self._mask_display(entry)

    def _mask_display(self, entry: KeyEntry) -> None:
        try:
            plain = self._engine.decrypt(entry.encrypted_key)
        except WrongPasswordError:
            plain = ""
        self.query_one("#d-key", Label).update(mask_key(plain))

    # --- 事件處理 ---

    def on_key(self, event: Any) -> None:
        self._idle = IDLE_LOCK_SECONDS

    def on_click(self, event: Any) -> None:
        self._idle = IDLE_LOCK_SECONDS

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._idle = IDLE_LOCK_SECONDS
        self._refresh_detail()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_copy()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if isinstance(event.button, CategoryButton):
            self._cat = event.button.category_name or None
            self._reload()
        elif button_id == "add-btn":
            self.action_add()
        elif button_id == "copy-btn":
            self.action_copy()
        elif button_id == "reveal-btn":
            self.action_reveal()
        elif button_id == "rename-btn":
            self.action_rename()
        elif button_id == "del-btn":
            self.action_delete()
        elif button_id == "lock-btn":
            self._lock()

    # --- 動作 ---

    def action_copy(self) -> None:
        entry = self._current_entry()
        if entry is None:
            self.notify("請先選取服務", severity="warning")
            return
        try:
            plain = self._engine.decrypt(entry.encrypted_key)
        except WrongPasswordError:
            self.notify("❌ 解密失敗", severity="error")
            return
        ttl = self._config.clipboard_ttl
        try:
            copy_to_clipboard(plain, ttl=ttl)
        except Exception as exc:
            self.notify(f"❌ 剪貼簿無法使用:{exc}", severity="error")
            return
        suffix = f",{ttl} 秒後自動清除" if ttl > 0 else ""
        self.notify(f"📋 {entry.service} 已複製到剪貼簿{suffix}")

    def action_reveal(self) -> None:
        entry = self._current_entry()
        if entry is None:
            self.notify("請先選取服務", severity="warning")
            return
        try:
            plain = self._engine.decrypt(entry.encrypted_key)
        except WrongPasswordError:
            self.notify("❌ 解密失敗", severity="error")
            return
        self.query_one("#d-key", Label).update(plain)

        def _remask() -> None:
            current = self._current_entry()
            if current is not None:
                self._mask_display(current)

        if self._reveal_timer is not None:
            self._reveal_timer.stop()
        self._reveal_timer = self.set_timer(REVEAL_SECONDS, _remask)

    def action_add(self) -> None:
        existing = {e.service for e in self._entries}
        self.app.push_screen(AddKeyModal(existing), self._on_add)

    def _on_add(self, data: Any) -> None:
        if not data:
            self._table().focus()
            return
        service = data["service"]
        try:
            encrypted = self._engine.encrypt(data["key"])
            self._store.save(
                service, encrypted, category=data["category"], note=data["note"]
            )
        except Exception as exc:
            self.notify(f"❌ 儲存失敗:{exc}", severity="error")
            self._table().focus()
            return
        self._reload(keep=service)
        self.notify(f"✅ {service} 已加密儲存至雲端")
        self._table().focus()

    def action_rename(self) -> None:
        entry = self._current_entry()
        if entry is None:
            self.notify("請先選取服務", severity="warning")
            return
        existing = {e.service for e in self._entries}
        self.app.push_screen(RenameModal(entry.service, existing), self._on_rename)

    def _on_rename(self, new_name: Any) -> None:
        entry = self._current_entry()
        if not new_name or entry is None:
            self._table().focus()
            return
        old_name = entry.service
        try:
            self._store.rename(old_name, new_name)
        except Exception as exc:
            self.notify(f"❌ {exc}", severity="error")
            self._table().focus()
            return
        self._reload(keep=new_name)
        self.notify(f"✅ 已將 '{old_name}' 重新命名為 '{new_name}'")
        self._table().focus()

    def action_delete(self) -> None:
        entry = self._current_entry()
        if entry is None:
            self.notify("請先選取服務", severity="warning")
            return
        self.app.push_screen(DeleteConfirmModal(entry.service), self._on_delete)

    def _on_delete(self, confirmed: Any) -> None:
        entry = self._current_entry()
        if not confirmed or entry is None:
            self._table().focus()
            return
        service = entry.service
        try:
            self._store.delete(service)
        except Exception as exc:
            self.notify(f"❌ 刪除失敗:{exc}", severity="error")
            self._table().focus()
            return
        self._reload()
        self.notify(f"🗑 已刪除 {service}")
        self._table().focus()

    def action_lock(self) -> None:
        self._lock()

    # --- 自動鎖定 ---

    def _tick_idle(self) -> None:
        self._idle -= 1
        if self._idle <= 0:
            self._lock(auto=True)
            return
        self.query_one("#locktimer", Label).update(
            f"⏱ {self._idle // 60:02d}:{self._idle % 60:02d}"
        )

    def _lock(self, auto: bool = False) -> None:
        if auto:
            self.notify("🔒 閒置逾時,已自動鎖定", timeout=6)
        self._engine = None  # 儘快丟棄金鑰材料
        self._entries = []
        self.app.switch_screen(UnlockScreen(self._config, self._store))


class AnyApiKeyApp(App[None]):
    """AnyApiKey 主應用程式(Textual TUI)。"""

    TITLE = "🔐 AnyApiKey"
    CSS = _CSS

    BINDINGS = [Binding("ctrl+q", "quit", "離開", priority=True)]

    def __init__(self, config: Config, store: KeyStore) -> None:
        super().__init__()
        self._config = config
        self._store = store

    def _get_dom_base(self) -> DOMNode:
        """讓 App 的 DOM 查詢預設對焦在當前活躍螢幕。"""
        return self.screen

    def on_mount(self) -> None:
        self.push_screen(UnlockScreen(self._config, self._store))
