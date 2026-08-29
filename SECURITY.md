# Security Policy — NeuraX Launcher

> **Version 4.0.0** — last updated 2026-08-29.

NeuraX is a locally-run Minecraft launcher. It does not host a backend service of its own, but it does talk to several third-party services (Microsoft, Mojang, Modrinth, mcsrvstat.us, DuckDuckGo, YouTube, Reddit). This document explains what data is exchanged, how it is stored, and how to report a vulnerability.

---

## 1. Supported Versions

| Version | Supported |
|---|---|
| 4.0.x  | ✅ Active development — security fixes shipped promptly. |
| 3.x    | ⚠️ Critical fixes only. Please upgrade. |
| ≤ 2.x  | ❌ End of life. No longer receiving security updates. |

---

## 2. Threat Model

NeuraX is a desktop app running with the user's normal privileges. The realistic threats are:

- **Compromised remote endpoints** (e.g. a malicious response from a server list) trying to inject HTML or commands into the UI.
- **A malicious mod file** downloaded from Modrinth and run inside the launcher context.
- **Token theft** of the Microsoft refresh token, which would let an attacker sign in to the user's Mojang account.
- **Local privilege escalation** via a bug in the `MRPackConverterWorker` or `LocalServerRunner` that writes outside the intended folder.
- **Supply chain attacks** on the Python dependencies (`PyQt6`, `minecraft-launcher-lib`, etc.).

The threat model explicitly does **not** include: a network attacker on the same Wi-Fi, a multi-tenant server backend, or admin control of the user's machine. The launcher is single-user.

---

## 3. Data the Launcher Stores

| Data | Where | Why | Encryption |
|---|---|---|---|
| Microsoft refresh token | OS keychain via `keyring` (`"neurax_launcher"`) | Silent re-login | OS-managed (DPAPI on Windows, Keychain on macOS, libsecret on Linux) |
| Microsoft access token (short-lived) | `config.json` | Live play session | Plain (rotated every launch) |
| Username, UUID | `config.json` | UI / Mojang session lookup | Plain |
| Per-instance playtime analytics | `config.json` under `"analytics"` | Settings → Instance card | Plain |
| Smart Server Radar query cache (last 200) | `~/.neurax/cache/smart_server_cache.json` | 1-hour TTL to avoid re-crawling | Plain (no PII) |
| Minecraft log files | `~/.neurax/logs/` | Crash diagnostics | Plain |
| Screenshots | `~/.neurax/{screenshots,global/.minecraft/screenshots,instances/*/screenshots}/` | Gallery | Plain (your files) |

No file under any of these paths is sent off-device except:

- The Microsoft OAuth flow itself (handled by `minecraft-launcher_lib.microsoft_account`).
- Modrinth API queries when you use the Modrinth Hub (read-only search and download).
- `mcsrvstat.us` pings when you click a server in the Server Radar.
- DuckDuckGo / YouTube / Reddit fetches when you use the Server Radar.

The launcher does **not** ship a remote-deactivation endpoint, a kill switch, or a phone-home beacon. Public "kill switch" patterns (e.g. unauthenticated JSON endpoints) are a known anti-pattern — see [§7](#7-anti-patterns-we-do-not-use) below.

---

## 4. Microsoft Authentication

- The Microsoft OAuth client ID used by the launcher is the well-known public Minecraft client ID (`00000000402b5328`). This is not a secret.
- The redirect URL is `https://login.live.com/oauth20_desktop.srf`, the Microsoft standard.
- The refresh token is stored via `keyring`. **We never write it to `config.json`.** If `keyring` is unavailable, the launcher falls back to `config.json` and prints a one-time warning.
- A failed token refresh clears the keychain entry (`delete_secure_token("refresh_token")`) and forces the user back to the sign-in screen.

If you believe your refresh token has been compromised, sign out of the launcher (**Settings → Account → Sign Out**), then go to https://account.microsoft.com/privacy/app-activity and revoke the `Xbox` and `Minecraft` consents. That will invalidate the token on Microsoft's side regardless of what is stored locally.

---

## 5. Downloads and External Content

When you install a mod or modpack from Modrinth, the launcher downloads:

- The project `.jar` / `.mrpack` from Modrinth's CDN.
- Optional dependencies (declared in the modrinth index).
- The version manifest and asset index for the Minecraft version.

All downloads are streamed into `~/.neurax/instances/<name>/.minecraft/mods/` or into the mrpack temp directory. The launcher does **not** execute a downloaded `.jar` inside the launcher process. Mod jars are run by the user's `java` binary in a child process.

Modrinth URLs are validated to point at `cdn.modrinth.net` or `github.com` (for Modrinth-published GitHub releases) before download. Other origins are rejected.

---

## 6. Local Server Manager

The `LocalServerRunner` (see `neurax/core/local_server.py`) is a `QObject` that spawns a Minecraft server as a child process. The runner:

- Refuses to start a server if `active_runner.is_running` is already `True` (rapid double-click guard).
- Sends `stop` over stdin and falls back to a hard `process.kill()` after 6 s.
- Writes server logs into `~/.neurax/servers/<folder>/logs/`.

The runner does **not** open any inbound network port other than the Minecraft server port itself. It does not serve an HTTP admin API.

---

## 7. Anti-Patterns We Do Not Use

The following patterns are commonly seen in less-careful launchers and are **deliberately not present** in NeuraX:

- **Remote deactivation / kill switches via unauthenticated JSON endpoints.** A public URL that any visitor can toggle to "lock" a user out of the launcher is a denial-of-service vector. The launcher does not check any external "is this version still allowed" endpoint at boot.
- **Plaintext password storage.** Local lock screens (if any) use `keyring` for the passphrase hash, not `config.json`.
- **Auto-execution of downloaded jars in the launcher process.** Mods are launched in a child JVM, never in the launcher's own process.
- **Silent telemetry.** No device name, no directory listing, no usage ping. The `update_users_file` hook in `app.py` is the only optional network call, and it is gated by an explicit `import users` import.
- **Forced update of `options.txt` ignoring user choices.** The merge logic in `optimize_game_options` only fills in missing keys and only migrates a known short list of legacy values (`maxFps: 60 / 120 / 260`).

---

## 8. Reporting a Vulnerability

**Please do not open a public GitHub issue for security bugs.** Email the maintainer instead, or use GitHub's private vulnerability reporting:

- GitHub: **Settings → Security → Advisories → "New draft security advisory"** (preferred).
- Or open a private issue tagged `[security]` and the maintainer will convert it.

When reporting, please include:

- NeuraX version (`Help → About` or `version.txt`).
- Operating system and Python version (`python --version`).
- A minimal reproduction: which view, what you clicked, what you expected vs. what happened.
- If the report is about a dependency, name the package and version.

We aim to acknowledge security reports within **72 hours** and to ship a fix within **30 days** for anything rated High or Critical.

---

## 9. Dependencies and Supply Chain

NeuraX's runtime dependencies are pinned in `requirements.txt`. The launcher does not pull any dynamic code from the network at runtime — all Python is bundled at build time, and the only network calls are the documented ones (Microsoft, Mojang, Modrinth, mcsrvstat.us, DuckDuckGo, YouTube, Reddit).

We monitor CVEs in the top-level dependencies and ship a patch release within 7 days of any High or Critical CVE in:

- `PyQt6` (Qt)
- `minecraft-launcher-lib`
- `requests`
- `Pillow`
- `keyring`

---

## 10. Hardening Recommendations for Self-Hosters

If you distribute a build of NeuraX to other users, we recommend:

1. Sign the binary (Authenticode on Windows, `codesign` on macOS).
2. Pin the Python version in your build environment.
3. Run the smoke test (`python _smoke.py` in the repo) on each build to catch import-time regressions.
4. Verify `requirements.txt` hashes against a lockfile before shipping.
5. Encourage your users to enable **Settings → Account → Sign Out** when they uninstall.

---

## 11. Compliance

NeuraX is a personal/educational project. It is not certified under any specific security framework (SOC 2, ISO 27001, etc.). The Microsoft OAuth flow relies on the public Minecraft client ID, which is provided by Microsoft for use in launchers; using the launcher implies acceptance of Microsoft's terms.
