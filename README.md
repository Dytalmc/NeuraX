# NeuraX Launcher 🚀

> **Version 4.0.0** — Ultra-fast, glassmorphism Minecraft launcher built with Python 3.11+ and PyQt6.

NeuraX is a modern, performance-focused Minecraft launcher that ships with full instance isolation, Microsoft and offline authentication, dynamic version manifests, automatic Java detection, a Modrinth mod browser, an AI-assisted server radar, an in-house 2D/3D skin renderer, and a local game-server manager. It is designed to feel as fast and clean as a native Windows app while staying cross-platform friendly.

---

## Table of Contents
- [Highlights](#highlights)
- [Screenshots & UI](#screenshots--ui)
- [Feature Tour](#feature-tour)
- [Tech Stack](#tech-stack)
- [Installation](#installation)
- [First Run](#first-run)
- [Configuration](#configuration)
- [Performance Tuning](#performance-tuning)
- [Architecture](#architecture)
- [Telemetry & Privacy](#telemetry--privacy)
- [Security Policy](#security-policy)
- [Contributing](#contributing)
- [License](#license)
- [Changelog](#changelog)

---

## Highlights

| | |
|---|---|
| ⚡ **Instant boot** | Animated cyber-cockpit loading screen, QPropertyAnimation fades, no spinner stalls. |
| 🪟 **Glassmorphism UI** | `GlassCard`, blurred dialogs, animated sub-tabs, and a hover-reactive vector icon set rendered with QPainter. |
| 🧩 **Modrinth Hub** | Search, filter, and one-click install mods, modpacks, resource packs, shaders, and plugins. AI Mod Radar scores compatibility and impact. |
| 🤖 **Server Radar** | Zero-token rule-based discovery across DuckDuckGo, YouTube, and Reddit. Live `mcsrvstat.us` player count, version, and MOTD. |
| 🎮 **Local Server Manager** | Run a Paper / Fabric / Vanilla / Forge / NeoForge / Quilt / Spigot / Folia / Purpur server right from the launcher. |
| 🛡️ **Microsoft Auth** | Full OAuth flow with `keyring`-backed refresh token storage, silent re-login, and skin/cape sync. |
| 🎨 **Skin Studio** | Pick a `.png`, preview as Steve/Alex, upload to Mojang, or reset. Legacy 32×32 → 64×64 auto-upscale. |
| 🖼️ **Screenshot Gallery** | Aggregates every `.png` under `~/.neurax/{screenshots,global/.minecraft/screenshots,instances/*/screenshots}/`. |
| 🧠 **AI Crash Analyzer** | Pattern-matches Minecraft log output and recommends fixes, all local. |
| 🎨 **Live Theme** | Cyan / Purple / Orange / Emerald / Pink accent, full Dark / Light mode, persisted across launches. |

---

## Screenshots & UI

The launcher ships with a sidebar-driven navigation bar (Play, Instances, Versions, Modrinth, Servers, New Server, Gallery, Skins, AFK, News, Settings). Every view uses the same `GlassCard` + `AnimatedSubTabBar` building blocks, so the look is consistent across the app.

- **Play** view: large `PLAY` button (white text, bold Segoe UI Black, italic, 24 px), live diagnostic console drawer, AI Diagnose Log button, Copy / Clear actions.
- **Instances** view: create, edit, delete, reinstall, MRPack convert, instance-scoped RAM slider.
- **Modrinth** view: live-search bar, project type / loader / version / sort filters, project cards with icon loader, AI score badge, version installer with target destination chooser.
- **Servers** view: AI search bar (`high player fabric survival`, `play.hypixel.net`, `drdonut`, etc.), live radar, latency badges, one-click `Quick Join`.
- **Local Server** view: console drawer with stdin, RAM tuning, server folder selector.
- **Skins** view: Steve / Alex preview with second-layer overlay, Mojang cape rendering.
- **Gallery** view: card-grid of screenshots with source labels (e.g. `Fabric - 2612`, `global`).
- **Settings** view: theme + accent, Microsoft auth, RAM cap, JVM args, maintenance, Discord RPC toggle.

---

## Feature Tour

### 🎮 Play view
- Animated **PLAY** button (`HoverPlayButton`) with smooth QVariantAnimation hover, 220 ms OutCubic, accent-aware gradient.
- Auto-scroll diagnostic console, AI Diagnose Log button, Copy / Clear, **260 → uncapped** FPS migration.
- Per-instance pre-launch global sync hook (configurable).
- Close-on-launch support (minimizes to background mode).

### 🧩 Instances
- **Create / Edit / Delete** instances with loader, MC version, RAM, Java path, custom JVM args.
- **MRPack convert** to zip or to a working instance via the bundled `MRPackConverterWorker`.
- **Maintain** mode: 30-day log rotation, 0-byte / corrupt-jar repair.
- Per-instance analytics: total playtime, last session length, last played.

### 🧰 Modrinth Hub
- Live search on typing, 4-source parallel fetch (Modrinth API, AI Mod Radar, FetchProjectDataWorker, ImageLoaderThread).
- Project types: mod, modpack, resourcepack, shader, plugin, datapack.
- Loaders: Fabric, Forge, NeoForge, Quilt, Paper, Purpur, Folia, Spigot, Vanilla.
- Project inspector dialog with rich HTML description, versions tree, install to instance or local server.
- AI Mod Radar evaluates impact (Popularity × Downloads × Maintenance) and shows an A+ / B- / C grade badge.

### 🛰️ Server Radar
- **Zero-token discovery** across mcsrvstat.us, DuckDuckGo HTML, YouTube HTML, and Reddit (via `site:` filter).
- 20-entry curated seed list as a safety net so empty queries still return real, live servers.
- Owner-alias injection: typing `drdonut`, `wisp`, `rekrap`, `clownpierce`, etc. instantly surfaces the canonical community server.
- Structured extraction: name, owner, IP, loader, version, gamemode, min/max players, description.
- 1-hour persistent query cache at `~/.neurax/cache/smart_server_cache.json`.

### 🛡️ Local Server
- One-click Paper / Fabric / Vanilla / Forge / NeoForge / Quilt / Spigot / Folia / Purpur / Bukkit server.
- Live stdin console with command input, server `stop` and force-kill fallback.
- RAM cap, custom Java path, custom JVM args, headless start.
- Auto-update detection against installed server jar.

### 🎨 Skins
- Pick a custom `.png` (auto-upscale legacy 32×32 → 64×64, slim/classic auto-detection).
- Mojang upload (Microsoft-authenticated) and reset to default.
- 2-layer overlay preview, Mojang cape overlay, front/back/both views.

### 🖼️ Gallery
- Aggregates screenshots from `~/.neurax/screenshots/`, `~/.neurax/global/.minecraft/screenshots/`, and every `~/.neurax/instances/*/.minecraft/screenshots/`.
- Source chip on every card so you always know which instance a shot came from.
- Open the global folder, refresh, delete, click-to-open in OS viewer.

### 🧠 AI Crash Analyzer
- Pattern-matches log lines for known issues: missing Java, mod loader version mismatch, OpenGL driver failure, Java GC overhead, OutOfMemoryError, etc.
- Recommends a fix per diagnosis (e.g. *install Java 21 for 1.20.5+*).

### ⚙️ Settings
- **Theme**: Dark / Light, accent color picker.
- **Account**: Microsoft OAuth, silent re-login via keyring-stored refresh token, logout.
- **Performance**: RAM slider, JVM args editor with reset-to-default, FPS migration.
- **Maintenance**: log rotation, jar repair, cache cleanup.
- **Discord RPC**: presence toggle (Join / Spectate / Edit state).
- **AFK Mode**: idle screensaver (separate view).

---

## Tech Stack

- **Python** 3.11+ (tested on 3.11, 3.12, 3.13, 3.14)
- **PyQt6** ≥ 6.11
- **minecraft-launcher-lib** ≥ 8.0 — version manifest, install, Java downloader, auth.
- **requests** ≥ 2.28, **aiohttp** ≥ 3.8 — HTTP clients.
- **keyring** ≥ 25.7 — secure token storage (Windows Credential Manager / macOS Keychain / libsecret).
- **Pillow** ≥ 9.5 — image decoding.
- **pypresence** ≥ 4.3 — Discord Rich Presence.
- **mcstatus** ≥ 11.0 — server pinging fallback.
- **markdown** ≥ 3.4 — README / changelog rendering.
- **BeautifulSoup4** — HTML parsing for the server discovery crawler.

No LLM, no cloud AI, no API keys, no tokens. Server discovery, mod recommendations, crash analysis, and the skin UI are all rule-based and run locally.

---

## Installation

### Windows (recommended)
1. Download the latest `NeuraX.exe` from the Releases page.
2. Run it — the launcher stores everything under `%APPDATA%\.neurax\`.
3. Sign in with Microsoft (optional) or use offline mode.

### From source
```bash
git clone https://github.com/Dytalmc/NeuraX
cd neurax
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
python main.py
```

> Python 3.14 works (we have an `asyncio.windows_utils` patch in `app.py` and `main.py` that monkey-patches the Proactor transport for clean shutdown on Windows).

---

## First Run

1. The cyber-cockpit loading screen scans Java, fetches telemetry, and launches the dashboard.
2. Pick an accent color and a mode (defaults: **Cyan** / **Dark**).
3. Go to **Instances** → create one, pick a Minecraft version, choose a loader (Fabric, Forge, NeoForge, Quilt, Paper, Vanilla, …).
4. Hit **PLAY**. The launcher will download the Java runtime, install the loader, and launch.

---

## Configuration

The launcher persists all settings to `%APPDATA%\.neurax\config.json` (or `~/.neurax/config.json` on macOS / Linux). Key fields:

```json
{
  "accent_color": "#00F0FF",
  "theme_mode": "dark",
  "selected_instance": "Fabric - 2612",
  "auth_mode": "microsoft",
  "username": "Dytalmc",
  "uuid": "db1ab0ae82794764b964f432884ae667",
  "max_ram_mb": 6144,
  "java_path": "auto",
  "jvm_args": "-XX:+UseG1GC …",
  "close_on_launch": false,
  "discord_rpc": true,
  "global_sync_enabled": false,
  "skin_model": "classic"
}
```

Sensitive tokens (Microsoft refresh token) are stored in the OS keychain via `keyring`, not in `config.json`.

---

## Performance Tuning

- The launcher applies these defaults to `options.txt` on every launch (only when the key is missing or empty, and migrating the legacy `maxFps: 260 / 120 / 60` to uncapped `0`):
  - `maxFps: 0` (uncapped)
  - `enableVsync: false`
  - `renderClouds: false`
  - `pauseOnLostFocus: false`
  - `prioritizeChunkUpdates: 2`
  - `chunkBuilderMode: 1`
  - `entityShadows: false`
  - `graphicsMode: 1` (Fancy — set to 0 in-game for Fast)
  - `fullscreen: true`
- For Sodium / Fabric setups, expect 500+ FPS on a modern CPU + dedicated GPU.
- JVM args default to a tuned G1GC profile (`MaxGCPauseMillis=20`, parallel ref processing, etc.). Edit in **Settings → Performance → JVM args**.

---

## Architecture

```
neurax/
├── main.py                  # Windows asyncio patch + entry point
├── app.py                   # QApplication, LoadingScreen, main()
├── core/
│   ├── launcher.py          # LaunchWorker, options.txt optimiser, JVM/Java resolver
│   ├── local_server.py      # LocalServerRunner (QObject + subprocess)
│   ├── instances.py         # InstanceManager (CRUD over ~/.neurax/instances/)
│   ├── versions.py          # VersionManager (manifests, asset index, library resolver)
│   ├── modrinth.py          # ModrinthAPI + ModrinthSearchWorker / ModrinthInstallWorker
│   ├── mrpack.py            # MRPackConverterWorker (zip or instance)
│   ├── skin.py              # SkinDownloader (QThread) + 2D model renderer
│   ├── auth.py              # AuthManager (Microsoft OAuth + keyring)
│   ├── discord_rpc.py       # DiscordManager (pypresence wrapper)
│   ├── config.py            # ConfigManager (JSON-backed, thread-safe)
│   ├── maintenance.py       # Log rotation, jar repair
│   ├── server_pinger.py     # mcstatus-based server pinger
│   ├── java_finder.py       # Cross-platform Java discovery
│   ├── logger.py            # File + console logger
│   └── ai/
│       ├── ai_engine.py     # Tokeniser, cosine similarity, intent classifier
│       ├── ai_server_radar.py       # Compatibility shim → smart_server_discovery
│       ├── smart_server_discovery.py # 4-source crawler, scoring, cache
│       ├── ai_mod_radar.py          # Mod impact scorer
│       ├── ai_crash_analyzer.py     # Pattern-matches log output
│       └── ai_version_radar.py      # Version recommendation
├── gui/
│   ├── main_window.py       # Sidebar nav, stack of views
│   ├── theme.py             # ButtonHoverFilter, Theme
│   ├── icons.py             # Vector icon set (QPainter)
│   ├── widgets/             # GlassCard, AnimatedStackedWidget, AnimatedSubTabBar, …
│   └── views/               # play, instances, versions, modrinth, servers, …
```

Every long-running task runs on a `QThread` or daemon `threading.Thread`; signals cross thread boundaries safely. QThread wrappers are **never** dropped while still running — see the `_retired_workers` pattern in `SkinView`, `GalleryView`, and `ModrinthView` for the canonical retirement helper.

---

## Telemetry & Privacy

- **No silent telemetry.** NeuraX does not log device names, scan local directories, or report usage data without explicit opt-in.
- **Optional maintenance telemetry** (`update_users_file`): if you imported `users.py` and called `update_users_file()`, only an anonymous running count is sent to the configured endpoint. The launcher itself never sends this.
- **Microsoft refresh tokens** are stored in the OS keychain via `keyring`, never in `config.json`.
- **All AI features run locally.** Server discovery, mod scoring, crash analysis, and skin rendering use no LLM, no API key, no token.
- **Discord Rich Presence** is opt-in and only active when `discord_rpc=true`.

See [`SECURITY.md`](./SECURITY.md) for the full security policy and how to report vulnerabilities.

---

## Contributing

Pull requests welcome. Before opening a PR:

1. Run the launcher at least once to confirm boot.
2. Add or update a smoke test if you change any module under `core/` or `core/ai/`.
3. Match the existing code style: 4-space indent, single-quote strings, type hints on public functions, docstrings on public classes.
4. Never introduce `except Exception: pass` without a comment explaining why.
5. Never replace a running `QThread` without going through the `_retired_workers` retirement pattern.

---

## License

NeuraX is released under the MIT License. See `LICENSE` for the full text.

---

## Changelog

### 4.0.0 (current)
- **Modrinth Hub rewrite** — `ModrinthProjectCard` icon loaders use a `_safe_set_pixmap` shiboken/exception guard to stop the "wrapped C/C++ object has been deleted" crash.
- **Server Radar** — new `smart_server_discovery` engine aggregates mcsrvstat.us, DuckDuckGo HTML, YouTube HTML, and Reddit (via `site:` filter). 20-server curated seed list. 1-hour query cache. 100% local, 0 tokens, 0 API keys.
- **.mrpack converter** — `MRPackConverterWorker` call site now correctly forwards `output_path` / `instance_name` (the old `target_name` / `config` mismatch crashed every conversion).
- **Instance dialog** — `get_system_ram_info()` was returning a tuple, not a dict; the `["total_mb"]` indexer is fixed to unpack positionally.
- **Skin picker** — `SkinView.reload_skin` now retires the previous `SkinDownloader` properly, fixing the "QThread: Destroyed while thread '' is still running" warning on rapid skin changes.
- **Modrinth search** — same retirement pattern added to `ModrinthView._do_search` for fast typing.
- **Local server** — `_start_server` double-click guard + `_on_server_stopped` clears the dead runner.
- **Instance MRPack convert** — double-click guard added.
- **Gallery** — aggregates screenshots from `~/.neurax/screenshots/`, `~/.neurax/global/.minecraft/screenshots/`, and every `~/.neurax/instances/*/.minecraft/screenshots/`. Source label on every card.
- **FPS migration** — `optimize_game_options` migrates legacy `maxFps: 260 / 120 / 60` to `0` (uncapped). `fullscreen: true` by default.
- **UI** — Play button is now white, bold, italic, says "PLAY". Console Copy / Clear / AI Diagnose buttons aligned to the Auto-scroll row.
- **Defaults** — explicit `theme_mode: dark` and `accent_color: "#00F0FF"` in `_DEFAULT_CONFIG`.

### Earlier
- 3.x: Microsoft auth, Modrinth integration, local server manager, glassmorphism UI, vector icon engine, AI crash analyzer, Discord RPC.
- 2.x: Initial Python/PyQt6 port, instance manager, version manager, basic launcher.
- 1.x: CLI prototype.
