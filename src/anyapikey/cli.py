"""CLI 模組 — 使用者互動介面。

基於 typer 的命令行工具，提供 API Key 的
新增、查詢、列表、刪除、重新命名等操作。
"""

from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from anyapikey import __version__
from anyapikey.clipboard import copy_to_clipboard
from anyapikey.config import Config, ConfigError
from anyapikey.crypto import CryptoEngine, WrongPasswordError
from anyapikey.store import KeyStore, StoreError

app = typer.Typer(
    name="anyapikey",
    help="🔐 AnyApiKey — 跨平台 API Key 加密管理工具",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

# --- 輔助函式 ---


def _load_config() -> Config:
    """載入設定檔。"""
    try:
        return Config.load()
    except Exception as exc:
        rprint(f"[red]❌ 載入設定失敗：{exc}[/red]")
        rprint("[yellow]提示：請先執行 'anyapikey init' 進行初始化[/yellow]")
        raise typer.Exit(1) from exc


def _connect_store(config: Config) -> KeyStore:
    """建立 Firestore 連線。"""
    try:
        return KeyStore(config.credentials_path)
    except StoreError as exc:
        rprint(f"[red]❌ {exc}[/red]")
        raise typer.Exit(1) from exc


def _ask_master_password(confirm: bool = False) -> str:
    """要求使用者輸入主密碼。

    Args:
        confirm: 是否要求二次確認（用於首次設定）。

    Returns:
        主密碼字串。
    """
    password = getpass.getpass("🔑 請輸入主密碼：")
    if not password:
        rprint("[red]❌ 主密碼不能為空[/red]")
        raise typer.Exit(1)

    if confirm:
        password2 = getpass.getpass("🔑 請再次輸入主密碼：")
        if password != password2:
            rprint("[red]❌ 兩次密碼不一致[/red]")
            raise typer.Exit(1)

    return password


def _get_crypto_engine(
    store: KeyStore,
    config: Config,
    password: str | None = None,
) -> CryptoEngine:
    """取得加密引擎（處理 salt 取得與密碼輸入，優先使用本地快取）。

    Args:
        store: Firestore 儲存庫。
        config: 設定檔實例（用於讀寫 salt 快取）。
        password: 主密碼（None 時互動式詢問）。

    Returns:
        CryptoEngine 實例。
    """
    # 優先從本地快取讀取 salt
    salt = config.salt

    if salt is None:
        # 本地無快取，從遠端 Firestore 獲取
        salt = store.get_salt()
        if salt is None:
            rprint("[red]❌ 尚未初始化，請先執行 'anyapikey init'[/red]")
            raise typer.Exit(1)
        # 快取到本地
        config.salt = salt

    if password is None:
        password = _ask_master_password()

    return CryptoEngine(password, salt)


# --- 命令實作 ---


@app.command()
def init() -> None:
    """🚀 首次設定引導精靈。"""
    rprint("\n[bold cyan]🚀 AnyApiKey 初始化精靈[/bold cyan]\n")

    # 步驟 1：載入/建立設定
    config = Config.load()
    rprint(f"[green]✅ 設定目錄：{config.config_dir}[/green]")

    # 步驟 2：檢查憑證檔案
    cred_path = config.credentials_path
    if not cred_path.exists():
        rprint(f"[yellow]⚠️  找不到 Firestore 憑證：{cred_path}[/yellow]")
        rprint(
            "[yellow]   請將 Service Account JSON 檔案放到上述路徑[/yellow]"
        )

        custom_path = typer.prompt(
            "或輸入自訂路徑（按 Enter 跳過）",
            default="",
            show_default=False,
        )
        if custom_path:
            custom = Path(custom_path).expanduser()
            if not custom.exists():
                rprint(f"[red]❌ 找不到檔案：{custom}[/red]")
                raise typer.Exit(1)
            config.credentials_path = str(custom)
            config.save()
            rprint(f"[green]✅ 已更新憑證路徑：{custom}[/green]")
        else:
            rprint("[red]❌ 需要 Firestore 憑證才能繼續[/red]")
            raise typer.Exit(1)

    # 步驟 3：測試連線
    rprint("\n[dim]📡 測試 Firestore 連線...[/dim]")
    store = _connect_store(config)
    store.test_connection()
    rprint("[green]✅ Firestore 連線正常[/green]")

    # 步驟 4：檢查/生成 salt
    existing_salt = store.get_salt()
    if existing_salt:
        rprint("[green]✅ 偵測到已有加密設定（從其他裝置同步）[/green]")
        rprint("[dim]   將使用現有的加密 salt[/dim]")
        config.salt = existing_salt
    else:
        rprint("\n[dim]🔐 生成加密 salt...[/dim]")
        salt = CryptoEngine.generate_salt()
        store.save_salt(salt)
        config.salt = salt
        rprint("[green]✅ 加密 salt 已儲存至 Firestore 與本地快取[/green]")

        # 首次設定：要求設定主密碼（僅用於驗證，不儲存）
        rprint("\n[bold]請設定主密碼（此密碼不會被儲存，請務必牢記）[/bold]")
        _ask_master_password(confirm=True)
        rprint("[green]✅ 主密碼設定完成[/green]")

    rprint("\n[bold green]🎉 初始化完成！[/bold green]")
    rprint("[dim]現在可以使用 'anyapikey set <服務名稱>' 來儲存 API Key[/dim]\n")


@app.command(name="set")
def set_key(
    service: str = typer.Argument(help="服務名稱（如 OpenAI, Anthropic）"),
    key: str | None = typer.Argument(None, help="API Key（留空則互動式輸入）"),
    category: str = typer.Option("", "--category", "-c", help="分類標籤"),
    note: str = typer.Option("", "--note", "-n", help="備註說明"),
    force: bool = typer.Option(False, "--force", "-f", help="已存在時直接覆蓋"),
) -> None:
    """💾 儲存或更新一筆 API Key。"""
    config = _load_config()
    store = _connect_store(config)

    # 檢查是否已存在
    if store.exists(service) and not force:
        overwrite = typer.confirm(f"'{service}' 已存在，是否覆蓋？")
        if not overwrite:
            rprint("[yellow]已取消[/yellow]")
            raise typer.Exit(0)

    # 取得 API Key
    if key is None:
        key = getpass.getpass(f"🔑 請輸入 {service} 的 API Key：")
        if not key:
            rprint("[red]❌ API Key 不能為空[/red]")
            raise typer.Exit(1)

    # 加密並儲存
    engine = _get_crypto_engine(store, config)
    encrypted = engine.encrypt(key)
    store.save(service, encrypted, category=category, note=note)
    rprint(f"[green]✅ {service} 已加密儲存至雲端[/green]")


@app.command(name="get")
def get_key(
    service: str = typer.Argument(help="服務名稱"),
    show: bool = typer.Option(False, "--show", "-s", help="在終端機顯示明文"),
    no_copy: bool = typer.Option(False, "--no-copy", help="不複製到剪貼簿"),
) -> None:
    """🔍 查詢 API Key（預設複製到剪貼簿）。"""
    config = _load_config()
    store = _connect_store(config)

    entry = store.get(service)
    if entry is None:
        rprint(f"[red]❌ 找不到服務：{service}[/red]")
        raise typer.Exit(1)

    engine = _get_crypto_engine(store, config)

    try:
        decrypted = engine.decrypt(entry.encrypted_key)
    except WrongPasswordError:
        rprint("[red]❌ 主密碼錯誤[/red]")
        raise typer.Exit(1)

    # 複製到剪貼簿
    if not no_copy and config.auto_copy:
        ttl = config.clipboard_ttl
        copy_to_clipboard(decrypted, ttl=ttl)
        if ttl > 0:
            rprint(
                f"[green]🔑 {service} 的 API Key 已複製到剪貼簿"
                f"（{ttl} 秒後自動清除）[/green]"
            )
        else:
            rprint(f"[green]🔑 {service} 的 API Key 已複製到剪貼簿[/green]")

    # 顯示明文
    if show:
        rprint(f"[bold]🔑 {service}:[/bold] {decrypted}")

    # 顯示附加資訊
    if entry.category:
        rprint(f"[dim]   分類：{entry.category}[/dim]")
    if entry.note:
        rprint(f"[dim]   備註：{entry.note}[/dim]")


@app.command(name="list")
def list_keys(
    category: str | None = typer.Option(None, "--category", "-c", help="依分類篩選"),
    sort: str = typer.Option("name", "--sort", help="排序方式：name | category | updated"),
) -> None:
    """📋 列出所有已儲存的服務。"""
    config = _load_config()
    store = _connect_store(config)

    entries = store.list_all(category=category)

    if not entries:
        if category:
            rprint(f"[yellow]沒有分類為 '{category}' 的 API Key[/yellow]")
        else:
            rprint("[yellow]尚未儲存任何 API Key[/yellow]")
            rprint("[dim]使用 'anyapikey set <服務名稱>' 來新增[/dim]")
        return

    # 排序
    if sort == "category":
        entries.sort(key=lambda e: (e.category or "", e.service))
    elif sort == "updated":
        entries.sort(key=lambda e: e.updated_at, reverse=True)
    else:
        entries.sort(key=lambda e: e.service.lower())

    # 建立表格
    table = Table(
        title="🔐 已儲存的 API Key",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("服務名稱", style="bold white")
    table.add_column("分類", style="green")
    table.add_column("備註", style="dim")
    table.add_column("最後更新", style="yellow")

    for entry in entries:
        updated = entry.updated_at.strftime("%Y-%m-%d %H:%M")
        table.add_row(
            entry.service,
            entry.category or "-",
            entry.note or "-",
            updated,
        )

    console.print(table)
    rprint(f"\n[dim]共 {len(entries)} 筆[/dim]")


@app.command()
def delete(
    service: str = typer.Argument(help="服務名稱"),
    force: bool = typer.Option(False, "--force", "-f", help="不詢問確認"),
) -> None:
    """🗑️ 刪除一筆 API Key。"""
    config = _load_config()
    store = _connect_store(config)

    if not store.exists(service):
        rprint(f"[red]❌ 找不到服務：{service}[/red]")
        raise typer.Exit(1)

    if not force:
        confirmed = typer.confirm(f"確定要刪除 '{service}' 的 API Key？此操作無法復原")
        if not confirmed:
            rprint("[yellow]已取消[/yellow]")
            raise typer.Exit(0)

    store.delete(service)
    rprint(f"[green]✅ 已刪除 {service}[/green]")


@app.command()
def rename(
    old_name: str = typer.Argument(help="原服務名稱"),
    new_name: str = typer.Argument(help="新服務名稱"),
) -> None:
    """✏️ 重新命名服務名稱。"""
    config = _load_config()
    store = _connect_store(config)

    try:
        store.rename(old_name, new_name)
        rprint(f"[green]✅ 已將 '{old_name}' 重新命名為 '{new_name}'[/green]")
    except StoreError as exc:
        rprint(f"[red]❌ {exc}[/red]")
        raise typer.Exit(1) from exc


@app.command(name="config")
def config_cmd(
    key: str | None = typer.Argument(None, help="設定鍵（如 behavior.auto_copy）"),
    value: str | None = typer.Argument(None, help="新值"),
) -> None:
    """⚙️ 查看或修改設定。"""
    config = _load_config()

    if key is None:
        # 顯示所有設定
        rprint("\n[bold cyan]⚙️  目前設定[/bold cyan]\n")

        all_settings = config.display_all()
        for section, values in all_settings.items():
            rprint(f"[bold][{section}][/bold]")
            for k, v in values.items():
                rprint(f"  {k} = [green]{v}[/green]")
            rprint()

        rprint(f"[dim]設定檔位置：{config.config_file}[/dim]\n")
        return

    if value is None:
        # 顯示單一設定值
        try:
            v = config.get(key)
            rprint(f"{key} = [green]{v}[/green]")
        except ConfigError as exc:
            rprint(f"[red]❌ {exc}[/red]")
            raise typer.Exit(1) from exc
        return

    # 修改設定
    try:
        config.set(key, value)
        rprint(f"[green]✅ 已更新：{key} = {value}[/green]")
    except ConfigError as exc:
        rprint(f"[red]❌ {exc}[/red]")
        raise typer.Exit(1) from exc


@app.command(name="export")
def export_keys(
    output: Path = typer.Option(
        Path("./anyapikey-export.json.enc"),
        "--output",
        "-o",
        help="輸出檔案路徑",
    ),
) -> None:
    """📦 匯出所有 Key 至加密 JSON 檔案。"""
    config = _load_config()
    store = _connect_store(config)

    entries = store.list_all()
    if not entries:
        rprint("[yellow]沒有任何 Key 可匯出[/yellow]")
        raise typer.Exit(0)

    # 用目前主密碼解密所有 Key
    engine = _get_crypto_engine(store, config)

    export_data = []
    for entry in entries:
        try:
            decrypted = engine.decrypt(entry.encrypted_key)
        except WrongPasswordError:
            rprint("[red]❌ 主密碼錯誤[/red]")
            raise typer.Exit(1)

        export_data.append({
            "service": entry.service,
            "key": decrypted,
            "category": entry.category,
            "note": entry.note,
        })

    # 用匯出密碼重新加密
    rprint("\n[bold]請設定匯出密碼（可與主密碼不同）[/bold]")
    export_password = _ask_master_password(confirm=True)
    export_salt = CryptoEngine.generate_salt()
    export_engine = CryptoEngine(export_password, export_salt)

    payload = json.dumps(export_data, ensure_ascii=False)
    encrypted_payload = export_engine.encrypt(payload)

    # 寫入檔案
    export_file = {
        "version": 1,
        "salt": CryptoEngine.salt_to_str(export_salt),
        "data": encrypted_payload,
    }

    with open(output, "w", encoding="utf-8") as f:
        json.dump(export_file, f, ensure_ascii=False, indent=2)

    rprint(f"\n[green]✅ 已匯出 {len(export_data)} 筆 Key 至 {output}[/green]")


@app.command(name="import")
def import_keys(
    input_file: Path = typer.Option(
        ..., "--input", "-i", help="加密 JSON 檔案路徑", exists=True
    ),
    merge: bool = typer.Option(False, "--merge", help="與現有 Key 合併"),
) -> None:
    """📥 從加密 JSON 檔案匯入 Key。"""
    config = _load_config()
    store = _connect_store(config)

    # 讀取匯出檔案
    with open(input_file, encoding="utf-8") as f:
        export_file = json.load(f)

    if export_file.get("version") != 1:
        rprint("[red]❌ 不支援的匯出檔案版本[/red]")
        raise typer.Exit(1)

    # 用匯出密碼解密
    export_salt = CryptoEngine.salt_from_str(export_file["salt"])
    export_password = getpass.getpass("🔑 請輸入匯出檔案的密碼：")
    export_engine = CryptoEngine(export_password, export_salt)

    try:
        payload = export_engine.decrypt(export_file["data"])
    except WrongPasswordError:
        rprint("[red]❌ 匯出密碼錯誤[/red]")
        raise typer.Exit(1)

    import_data = json.loads(payload)

    # 用目前主密碼重新加密並儲存
    engine = _get_crypto_engine(store, config)

    imported = 0
    skipped = 0
    for item in import_data:
        service = item["service"]
        if store.exists(service) and not merge:
            overwrite = typer.confirm(f"'{service}' 已存在，是否覆蓋？")
            if not overwrite:
                skipped += 1
                continue

        encrypted = engine.encrypt(item["key"])
        store.save(
            service,
            encrypted,
            category=item.get("category", ""),
            note=item.get("note", ""),
        )
        imported += 1

    rprint(f"\n[green]✅ 匯入完成：{imported} 筆成功[/green]")
    if skipped:
        rprint(f"[yellow]⏭️  跳過 {skipped} 筆（已存在）[/yellow]")


@app.command()
def verify() -> None:
    """🔐 驗證主密碼是否正確。"""
    config = _load_config()
    store = _connect_store(config)

    # 優先從本地快取取得 salt，沒有才從雲端拿
    salt = config.salt
    if salt is None:
        salt = store.get_salt()
        if salt is None:
            rprint("[red]❌ 尚未初始化[/red]")
            raise typer.Exit(1)
        config.salt = salt

    password = _ask_master_password()
    engine = CryptoEngine(password, salt)

    # 嘗試解密第一筆 Key 來驗證密碼
    entries = store.list_all()
    if not entries:
        rprint("[yellow]⚠️  沒有已儲存的 Key 可驗證，密碼格式正確但無法確認正確性[/yellow]")
        return

    first = store.get(entries[0].service)
    if first is None:
        rprint("[yellow]⚠️  無法取得驗證用的 Key[/yellow]")
        return

    try:
        engine.decrypt(first.encrypted_key)
        rprint("[green]✅ 主密碼正確[/green]")
    except WrongPasswordError:
        rprint("[red]❌ 主密碼錯誤[/red]")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """📌 顯示版本資訊。"""
    rprint(f"[bold cyan]AnyApiKey[/bold cyan] v{__version__}")


def _version_callback(value: bool) -> None:
    """版本號回呼函式。"""
    if value:
        rprint(f"[bold cyan]AnyApiKey[/bold cyan] v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    _version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="顯示版本號",
    ),
) -> None:
    """🔐 AnyApiKey — 跨平台 API Key 加密管理工具。"""


if __name__ == "__main__":
    app()
