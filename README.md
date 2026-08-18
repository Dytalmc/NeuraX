# NeuraX Launcher 🚀

NeuraX is an expert-engineered, ultra-fast Minecraft Launcher built with **Python 3.11+** and **PyQt6**. It features a modern glassmorphism interface, GPU-accelerated micro-interactions, full instance isolation, Microsoft & Offline authentication, dynamic version manifests, dynamic Java detection, and 3D head/body skin rendering.

---

## ✨ Features
- **Visuals:** Dark Glassmorphism, Neon dynamic accent colors (Cyan, Purple, Emerald, Orange), glow effects, and GPU-accelerated page transitions.
- **Strict Isolation:** Stores everything inside `%APPDATA%\.neurax` (or `~/.neurax` on Linux/macOS). Every instance maintains its own `.minecraft` directory.
- **Instant Auto-Save:** All preferences (RAM, Java path, selected instance, accent color, credentials) write immediately to `config.json` with zero manual save buttons required.
- **Authentication:** Microsoft OAuth 2.0 Device Code Flow + Offline/Cracked mode fallback.
- **Version Support:** Dynamic fetching of Mojang manifests (Releases, Snapshots, Betas, Alphas, Indevs).
- **Asynchronous Engine:** Background downloads and non-blocking game installation logic using Python workers and `aiohttp`/`requests`.
- **Java Auto-Detection:** Automatically scans Windows, macOS, and Linux system directories for installed JREs/JDKs.
- **Integrated Skin Viewer:** Downloads and displays 2D/3D skin avatars directly from Mojang & Crafatar APIs.

---

## 📁 Directory Structure
```text
.neurax/
├── config.json                 # Launcher configuration (auto-saved)
├── cache/                      # Manifests and skin cache
│   └── skins/
├── instances/                  # Isolated Minecraft instances
│   ├── Default/
│   │   ├── instance.json       # Instance config (version, RAM, JVM args)
│   │   └── .minecraft/         # Game files (mods, saves, resourcepacks)
└── logs/                       # Launcher and crash logs
```

---

## ✅ Current Compatibility Notes
- Minecraft 26.1+ requires Java 25.
- minecraft-launcher-lib 8.x is used for the current unified mod-loader API.
- Microsoft sign-in uses the Minecraft-compatible Live/Xbox device-code flow.

## 🛠️ Tech Stack & Architecture
- **UI Layer:** PyQt6 (QGraphicsDropShadowEffect, QPropertyAnimation, QSS with CSS variable replacements)
- **Launcher Backend:** `minecraft-launcher-lib` + custom async downloader
- **Auth Engine:** Microsoft Device Code OAuth + Keyring fallback
- **Threading Model:** Multi-threaded QThread workers decoupled from the main UI loop to maintain 60 FPS under heavy download tasks.
