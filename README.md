# openclaw-mini

A minimal, Python-first OpenClaw-style bot that intentionally supports only:
- Discord
- OpenAI Codex (Responses API)
- Basic `SOUL.md` + `skills/` behavior

## Why this repo

- Simpler to understand: very small codebase, no large gateway/plugin architecture.
- Python style: fast iteration with standard Python tooling, easy local debugging.
- Focused integrations: one model path (Codex) and one channel (Discord), fewer moving parts.
- Service-ready: includes launchd/systemd templates so it can run continuously on your machine.

## What this version keeps

- `SOUL.md`: core personality/system behavior file loaded on every message.
- `skills/`: lightweight skill cards (`*.md`) included as model context.
- Built-in slash-like text commands:
  - `/help`
  - `/ping`
  - `/skills`
  - `/soul`

## What this version intentionally removes

- Multi-channel adapters (except Discord)
- Complex routing, onboarding, pairing flows, UI, plugins, and gateway
- Advanced memory/session orchestration

## Quick start

1. Create virtual environment and install:

```bash
cd /path/to/openclaw-mini
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

2. Configure env:

```bash
cp .env.example .env
# then edit .env with your keys/tokens
```

Required:
- `OPENAI_API_KEY`
- `DISCORD_BOT_TOKEN`

Optional:
- `OPENAI_MODEL` (default: `gpt-5.3-codex`)
- `OPENAI_ENABLE_WEB_SEARCH` (default: `true`)
- `SOUL_PATH` (default: `SOUL.md`)
- `DISCORD_ALLOWED_CHANNEL_IDS` (comma-separated channel IDs)

3. Run:

```bash
openclaw-mini
```

## Discord setup notes

In Discord Developer Portal for your bot:
- Enable `MESSAGE CONTENT INTENT`
- Invite bot with permissions to read/send messages in your server

## Running as a macOS service (launchd)

1. Open `service/openclaw-mini.launchd.plist` and replace `__PROJECT_DIR__` with your absolute project path.
2. Copy plist:

```bash
mkdir -p ~/Library/LaunchAgents
cp service/openclaw-mini.launchd.plist ~/Library/LaunchAgents/ai.openclaw.mini.plist
```

3. Load service:

```bash
launchctl unload ~/Library/LaunchAgents/ai.openclaw.mini.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/ai.openclaw.mini.plist
launchctl start ai.openclaw.mini
```

4. Check logs:

```bash
tail -f <your_project_path>/service/openclaw-mini.out.log
tail -f <your_project_path>/service/openclaw-mini.err.log
```

## Running as a Linux service (systemd)

Open `service/openclaw-mini.service` and replace:
- `__SERVICE_USER__` with your Linux username
- `__PROJECT_DIR__` with your absolute project path

```bash
sudo cp service/openclaw-mini.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-mini
sudo systemctl status openclaw-mini
```
