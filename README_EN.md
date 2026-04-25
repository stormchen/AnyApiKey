# 🔐 AnyApiKey

A cross-platform, encrypted API Key manager — synced via Google Firestore.

[繁體中文](README.md) | English

## Features

- **Encryption First**: All API Keys are encrypted locally with Fernet (AES-128-CBC) before being uploaded to the cloud
- **Cross-Platform Sync**: Seamlessly sync between Mac / Windows / Linux via Google Firestore
- **Clipboard Integration**: Automatically copies retrieved keys to clipboard with a 30-second auto-clear
- **Category Management**: Organize API Keys with tags (e.g., AI, Cloud, Payment)
- **Export / Import**: Encrypted backup and cross-account migration support

## Installation

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Google Cloud account + Firebase project

### Steps

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

## Usage

### Basic Operations

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

### Configuration

```bash
# View all settings
uv run anyapikey config

# Modify settings
uv run anyapikey config behavior.clipboard_ttl 60
uv run anyapikey config behavior.auto_copy false
```

### Export / Import

```bash
# Export all Keys (encrypted JSON)
uv run anyapikey export -o ~/backup/keys.json.enc

# Import
uv run anyapikey import -i ~/backup/keys.json.enc
```

### Quick Access (Recommended)

Add an alias to your `~/.zshrc` or PowerShell Profile:

```bash
alias ak="uv run --project ~/Projects/AnyApiKey anyapikey"
```

Then simply use:

```bash
ak set OpenAI sk-xxxx --category AI
ak get OpenAI
ak list
```

## Firestore Setup

1. Go to [Firebase Console](https://console.firebase.google.com/) and create a new project
2. Enable **Cloud Firestore** and select your preferred region (e.g., `asia-east1`)
3. Navigate to **Project Settings → Service Accounts** and download the JSON key
4. Place the JSON file at `~/.anyapikey/service-account.json`

## Security Architecture

```
Master Password → PBKDF2-SHA256 (480K iterations + random salt) → Fernet Key
API Key Plaintext → Fernet.encrypt() → Ciphertext → Firestore
```

- Salt is randomly generated (`os.urandom(16)`) and stored in Firestore `_meta/crypto`
- Master password is **never stored anywhere**
- Clipboard auto-clears after 30 seconds by default
- Even if Firestore data is compromised, keys cannot be decrypted without the master password

## License

MIT License
