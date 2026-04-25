"""設定模組 — 管理 ~/.anyapikey/config.toml。

負責讀寫應用程式設定檔，包括 Firestore 憑證路徑、
剪貼簿行為、預設排序等設定。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w

# 預設設定目錄
_DEFAULT_CONFIG_DIR = Path.home() / ".anyapikey"

# 預設設定值
_DEFAULTS: dict[str, dict[str, Any]] = {
    "firestore": {
        "credentials_path": str(_DEFAULT_CONFIG_DIR / "service-account.json"),
    },
    "behavior": {
        "auto_copy": True,
        "clipboard_ttl": 30,
        "default_sort": "name",
    },
}


class ConfigError(Exception):
    """設定相關錯誤。"""


class Config:
    """應用程式設定管理。

    設定檔位於 ~/.anyapikey/config.toml，
    首次使用時自動建立預設設定。
    """

    def __init__(
        self,
        config_dir: Path | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """初始化設定。

        Args:
            config_dir: 設定目錄路徑（預設 ~/.anyapikey/）。
            data: 設定資料字典（預設載入預設值）。
        """
        self.config_dir = config_dir or _DEFAULT_CONFIG_DIR
        self.config_file = self.config_dir / "config.toml"
        self._data = data or self._deep_copy_defaults()

    @staticmethod
    def _deep_copy_defaults() -> dict[str, Any]:
        """深複製預設設定值。"""
        return {
            section: dict(values) for section, values in _DEFAULTS.items()
        }

    @classmethod
    def load(cls, config_dir: Path | None = None) -> Config:
        """載入設定檔，不存在則建立預設值。

        Args:
            config_dir: 設定目錄路徑。

        Returns:
            Config 實例。
        """
        instance = cls(config_dir=config_dir)

        if instance.config_file.exists():
            with open(instance.config_file, "rb") as f:
                file_data = tomllib.load(f)
            # 合併：檔案設定覆蓋預設值
            for section, values in instance._data.items():
                if section in file_data:
                    values.update(file_data[section])
        else:
            # 首次使用，建立目錄與預設設定檔
            instance.config_dir.mkdir(parents=True, exist_ok=True)
            instance.save()

        return instance

    def save(self) -> None:
        """將目前設定寫入 config.toml。"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "wb") as f:
            tomli_w.dump(self._data, f)

    @property
    def credentials_path(self) -> Path:
        """取得 Service Account JSON 的完整路徑（支援 ~ 展開）。"""
        raw = self._data["firestore"]["credentials_path"]
        return Path(raw).expanduser()

    @credentials_path.setter
    def credentials_path(self, path: str | Path) -> None:
        """設定 Service Account JSON 路徑。"""
        self._data["firestore"]["credentials_path"] = str(path)

    @property
    def auto_copy(self) -> bool:
        """查詢後是否自動複製到剪貼簿。"""
        return self._data["behavior"]["auto_copy"]

    @property
    def clipboard_ttl(self) -> int:
        """剪貼簿自動清除時間（秒），0 = 不清除。"""
        return self._data["behavior"]["clipboard_ttl"]

    @property
    def default_sort(self) -> str:
        """列表預設排序方式。"""
        return self._data["behavior"]["default_sort"]

    def get(self, dotted_key: str) -> Any:
        """以 section.key 格式取得設定值。

        Args:
            dotted_key: 如 "behavior.auto_copy"。

        Returns:
            設定值。

        Raises:
            ConfigError: 設定鍵不存在。
        """
        parts = dotted_key.split(".", 1)
        if len(parts) != 2:
            raise ConfigError(f"無效的設定鍵格式：{dotted_key}（應為 section.key）")

        section, key = parts
        if section not in self._data:
            raise ConfigError(f"未知的設定區段：{section}")
        if key not in self._data[section]:
            raise ConfigError(f"未知的設定鍵：{dotted_key}")

        return self._data[section][key]

    def set(self, dotted_key: str, value: Any) -> None:
        """以 section.key 格式設定值並儲存。

        Args:
            dotted_key: 如 "behavior.clipboard_ttl"。
            value: 新值（會自動嘗試型別轉換）。

        Raises:
            ConfigError: 設定鍵不存在。
        """
        parts = dotted_key.split(".", 1)
        if len(parts) != 2:
            raise ConfigError(f"無效的設定鍵格式：{dotted_key}（應為 section.key）")

        section, key = parts
        if section not in self._data:
            raise ConfigError(f"未知的設定區段：{section}")
        if key not in self._data[section]:
            raise ConfigError(f"未知的設定鍵：{dotted_key}")

        # 嘗試型別轉換
        current = self._data[section][key]
        if isinstance(current, bool):
            value = str(value).lower() in ("true", "1", "yes")
        elif isinstance(current, int):
            value = int(value)

        self._data[section][key] = value
        self.save()

    def display_all(self) -> dict[str, Any]:
        """回傳所有設定值（供顯示用）。"""
        return dict(self._data)
