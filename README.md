# 🔐 AnyApiKey

A cross-platform, encrypted API Key manager — synced via Google Firestore.  
跨平台 API Key 加密管理工具 — 使用 Google Firestore 雲端同步。

[English](#english) | [繁體中文](#繁體中文)

---

## English

### Features

- **Encryption First**: All API Keys are encrypted locally with Fernet (AES-128-CBC) before being uploaded to the cloud
- **Cross-Platform Sync**: Seamlessly sync between Mac / Windows / Linux via Google Firestore
- **Clipboard Integration**: Automatically copies retrieved keys to clipboard with a 30-second auto-clear
- **Category Management**: Organize API Keys with tags (e.g., AI, Cloud, Payment)
- **Export / Import**: Encrypted backup and cross-account migration support

### Installation

#### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Google Cloud account + Firebase project

#### Steps

```bash
# 1. Clone the repository
git clone https://github.com/your-username/AnyApiKey.git
cd AnyApiKey

# 2. Install dependencies
uv sync

# 3. Place Firestore credentials
mkdir -p ~/.anyapikey
cp /path/to/your/service-account.json ~/.anyapikey/service-account.json

# 4. Initialize
uv run anyapikey init
```

### Usage

#### Basic Operations

```bash
# Save an API Key
uv run anyapikey set OpenAI sk-proj-xxxx --category AI --note "For GPT-4o project"

# Retrieve a Key (auto-copies to clipboard)
uv run anyapikey get OpenAI

# Retrieve and display in terminal
uv run anyapikey get OpenAI --show

# List all Keys
uv run anyapikey list

# Filter by category
uv run anyapikey list --category AI

# Delete
uv run anyapikey delete OpenAI

# Rename
uv run anyapikey rename OpenAI openai-production
```

#### Configuration

```bash
# View all settings
uv run anyapikey config

# Modify settings
uv run anyapikey config behavior.clipboard_ttl 60
uv run anyapikey config behavior.auto_copy false
```

#### Export / Import

```bash
# Export all Keys (encrypted JSON)
uv run anyapikey export -o ~/backup/keys.json.enc

# Import
uv run anyapikey import -i ~/backup/keys.json.enc
```

#### Quick Access (Recommended)

To quickly use the `ak` command in your terminal, set up a shortcut based on your operating system:

##### macOS / Linux (`~/.zshrc` or `~/.bashrc`)
Add an alias:
```bash
alias ak="uv run --project ~/Projects/AnyApiKey anyapikey"
```

##### Windows (PowerShell `$PROFILE`)
In PowerShell, add a function to correctly pass arguments:
```powershell
function ak {
    uv run --project "$HOME\Projects\AnyApiKey" anyapikey $args
}
```

Then simply use:

```bash
ak set OpenAI sk-xxxx --category AI
ak get OpenAI
ak list
```

### Firestore Setup

1. Go to [Firebase Console](https://console.firebase.google.com/) and create a new project
2. Enable **Cloud Firestore** and select your preferred region (e.g., `asia-east1`)
3. Navigate to **Project Settings → Service Accounts** and download the JSON key
4. Place the JSON file at `~/.anyapikey/service-account.json`

### Security Architecture

```
Master Password → PBKDF2-SHA256 (480K iterations + random salt) → Fernet Key
API Key Plaintext → Fernet.encrypt() → Ciphertext → Firestore
```

- Salt is randomly generated (`os.urandom(16)`) and stored in Firestore `_meta/crypto`
- Master password is **never stored anywhere**
- Clipboard auto-clears after 30 seconds by default
- Even if Firestore data is compromised, keys cannot be decrypted without the master password

### License

MIT License

---

## 繁體中文

### 特色

- **加密優先**：所有 API Key 在本地使用 Fernet (AES-128-CBC) 加密後才上傳至雲端
- **跨平台同步**：透過 Google Firestore 在 Mac / Windows / Linux 之間無縫同步
- **剪貼簿整合**：查詢後自動複製到剪貼簿，預設 30 秒後自動清除
- **分類管理**：API Key 可依分類標籤組織（如 AI, Cloud, Payment）
- **匯出/匯入**：支援加密備份與跨帳號遷移

### 安裝

#### 前置條件

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)（Python 套件管理器）
- Google Cloud 帳號 + Firebase 專案

#### 步驟

```bash
# 1. 取得原始碼
git clone https://github.com/your-username/AnyApiKey.git
cd AnyApiKey

# 2. 安裝依賴
uv sync

# 3. 放置 Firestore 憑證
mkdir -p ~/.anyapikey
cp /path/to/your/service-account.json ~/.anyapikey/service-account.json

# 4. 初始化
uv run anyapikey init
```

### 使用方式

#### 基本操作

```bash
# 儲存 API Key
uv run anyapikey set OpenAI sk-proj-xxxx --category AI --note "GPT-4o 專案用"

# 查詢 Key（自動複製到剪貼簿）
uv run anyapikey get OpenAI

# 查詢並顯示明文
uv run anyapikey get OpenAI --show

# 列出所有 Key
uv run anyapikey list

# 依分類篩選
uv run anyapikey list --category AI

# 刪除
uv run anyapikey delete OpenAI

# 重新命名
uv run anyapikey rename OpenAI openai-production
```

#### 設定管理

```bash
# 查看所有設定
uv run anyapikey config

# 修改設定
uv run anyapikey config behavior.clipboard_ttl 60
uv run anyapikey config behavior.auto_copy false
```

#### 匯出 / 匯入

```bash
# 匯出所有 Key（加密 JSON）
uv run anyapikey export -o ~/backup/keys.json.enc

# 匯入
uv run anyapikey import -i ~/backup/keys.json.enc
```

#### 快速存取（建議）

為了能在終端機快速使用 `ak` 指令，請根據你的作業系統設定命令捷徑：

##### macOS / Linux (`~/.zshrc` 或 `~/.bashrc`)
加入 alias：
```bash
alias ak="uv run --project ~/Projects/AnyApiKey anyapikey"
```

##### Windows (PowerShell `$PROFILE`)
在 PowerShell 由於命令捷徑需要傳遞參數，請加入 Function：
```powershell
function ak {
    uv run --project "$HOME\Projects\AnyApiKey" anyapikey $args
}
```

之後就能用：

```bash
ak set OpenAI sk-xxxx --category AI
ak get OpenAI
ak list
```

### Firestore 設定

1. 前往 [Firebase Console](https://console.firebase.google.com/) 建立新專案
2. 啟動 **Cloud Firestore**，選擇 `asia-east1`（台灣彰化）
3. 在「專案設定 → 服務帳號」下載 JSON 金鑰
4. 將 JSON 放到 `~/.anyapikey/service-account.json`

### 安全架構

```
主密碼 → PBKDF2-SHA256 (480K iterations + random salt) → Fernet 金鑰
API Key 明文 → Fernet.encrypt() → 密文 → Firestore
```

- Salt 隨機生成（`os.urandom(16)`），儲存在 Firestore `_meta/crypto`
- 主密碼**不儲存在任何地方**
- 剪貼簿預設 30 秒後自動清除
- 即使 Firestore 資料外洩，沒有主密碼也無法解密

### 授權

MIT License
