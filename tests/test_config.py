"""設定模組單元測試。"""

import pytest
from pathlib import Path
from anyapikey.config import Config, ConfigError


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    """建立暫存設定目錄。"""
    config_dir = tmp_path / ".anyapikey"
    config_dir.mkdir()
    return config_dir


class TestConfig:
    """Config 測試。"""

    def test_load_creates_default(self, tmp_config_dir: Path) -> None:
        """首次載入應建立預設設定檔。"""
        config = Config.load(config_dir=tmp_config_dir)
        assert config.config_file.exists()
        assert config.auto_copy is True
        assert config.clipboard_ttl == 30
        assert config.default_sort == "name"

    def test_set_and_get(self, tmp_config_dir: Path) -> None:
        """設定值後應能正確取得。"""
        config = Config.load(config_dir=tmp_config_dir)
        config.set("behavior.clipboard_ttl", "60")
        assert config.get("behavior.clipboard_ttl") == 60

    def test_set_bool_conversion(self, tmp_config_dir: Path) -> None:
        """布林值應正確轉換。"""
        config = Config.load(config_dir=tmp_config_dir)
        config.set("behavior.auto_copy", "false")
        assert config.auto_copy is False

        config.set("behavior.auto_copy", "true")
        assert config.auto_copy is True

    def test_get_invalid_key(self, tmp_config_dir: Path) -> None:
        """無效的設定鍵應拋出 ConfigError。"""
        config = Config.load(config_dir=tmp_config_dir)

        with pytest.raises(ConfigError):
            config.get("nonexistent.key")

        with pytest.raises(ConfigError):
            config.get("behavior.nonexistent")

        with pytest.raises(ConfigError):
            config.get("invalid_format")

    def test_persistence(self, tmp_config_dir: Path) -> None:
        """設定變更應在重新載入後保持。"""
        config1 = Config.load(config_dir=tmp_config_dir)
        config1.set("behavior.clipboard_ttl", "120")

        config2 = Config.load(config_dir=tmp_config_dir)
        assert config2.clipboard_ttl == 120

    def test_credentials_path(self, tmp_config_dir: Path) -> None:
        """憑證路徑應正確展開 ~。"""
        config = Config.load(config_dir=tmp_config_dir)
        path = config.credentials_path
        assert isinstance(path, Path)
        assert "~" not in str(path)

    def test_display_all(self, tmp_config_dir: Path) -> None:
        """display_all 應回傳所有設定區段。"""
        config = Config.load(config_dir=tmp_config_dir)
        all_settings = config.display_all()
        assert "firestore" in all_settings
        assert "behavior" in all_settings
