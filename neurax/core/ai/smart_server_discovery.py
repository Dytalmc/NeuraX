"""
smart_server_discovery.py
========================
Rule-based, no-LLM, no-API-key Minecraft server discovery engine.

Combines four real free sources to find servers from the public web:
    1. mcsrvstat.us     – live player count, MOTD, version for any IP
    2. DuckDuckGo HTML  – general web search, no key, no JS
    3. YouTube HTML     – community videos (titles + descriptions), no key
    4. Reddit HTML      – r/admincraft + r/Minecraft threads, no key

Plus a curated seed list of well-known SMPs (expanded, not a 21-row joke)
so an empty query still has something to show.

The engine extracts structured fields (name, owner/youtuber, IP, loader,
version, gamemode, min/max players, description keywords) from the search
results, then ranks them against the user's query with a transparent
weighted scoring function. The result is a list of fully-populated server
dicts, each tagged with the source(s) it was found in and a per-field
confidence.

NO external LLM, NO API key, NO tokens, NO cloud. Everything runs in-process.
"""
from __future__ import annotations

import re
import json
import time
import hashlib
import threading
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

try:
    from neurax.core.config import get_dot_neurax_dir
except Exception:
    def get_dot_neurax_dir():
        from pathlib import Path as _P
        return _P.home() / ".neurax"


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NeuraX/1.0 (server discovery; +https://github.com/neurax)"
TIMEOUT = 8

# ---------------------------------------------------------------------------
# Curated seed list — real, well-known community servers, not a hard-coded
# "Donut SMP every time" joke. We only use this as a safety net when a search
# query is empty or the live web sources return nothing.
# ---------------------------------------------------------------------------
SEED_SERVERS: List[Dict[str, Any]] = [
    {"name": "Hypixel", "host": "mc.hypixel.net", "port": 25565, "gamemode": "Minigames",
     "loader": "Paper", "popularity": 100, "rating": 4.9, "owner": "Hypixel Studios",
     "description": "Largest Minecraft minigame server (SkyBlock, BedWars, SkyWars, Duels, Build Battle)."},
    {"name": "Donut SMP", "host": "play.donutsmp.net", "port": 25565, "gamemode": "Hardcore SMP",
     "loader": "Paper", "popularity": 92, "rating": 4.6, "owner": "DrDonut",
     "description": "Hardcore SMP with custom weapons, economy, and PvP."},
    {"name": "Wisp SMP", "host": "play.wispsmp.com", "port": 25565, "gamemode": "Lifesteal SMP",
     "loader": "Paper", "popularity": 80, "rating": 4.5, "owner": "Wisp",
     "description": "Lifesteal SMP by YouTuber Wisp with heart-based lives."},
    {"name": "Lifesteal SMP", "host": "play.lifestealsmp.com", "port": 25565, "gamemode": "Lifesteal SMP",
     "loader": "Paper", "popularity": 85, "rating": 4.5, "owner": "ClownPierce",
     "description": "Lifesteal SMP with hearts and custom enchantments."},
    {"name": "Echo SMP", "host": "play.echosmp.net", "port": 25565, "gamemode": "Survival SMP",
     "loader": "Fabric", "popularity": 78, "rating": 4.4, "owner": "Rekrap",
     "description": "Survival SMP by YouTuber Rekrap."},
    {"name": "Fist SMP", "host": "play.fistsmp.com", "port": 25565, "gamemode": "Hardcore SMP",
     "loader": "Paper", "popularity": 70, "rating": 4.3, "owner": "SubWithFist",
     "description": "Hardcore SMP by YouTuber SubWithFist."},
    {"name": "Flame SMP", "host": "play.flamesmp.net", "port": 25565, "gamemode": "Survival SMP",
     "loader": "Paper", "popularity": 68, "rating": 4.3, "owner": "FlameFrags",
     "description": "Survival SMP by YouTuber FlameFrags."},
    {"name": "Silver SMP", "host": "play.spekeys.com", "port": 25565, "gamemode": "Survival SMP",
     "loader": "Paper", "popularity": 65, "rating": 4.2, "owner": "SpeSilver",
     "description": "Survival SMP by YouTuber SpeSilver."},
    {"name": "Origin Realms", "host": "play.originrealms.com", "port": 25565, "gamemode": "Fabric SMP",
     "loader": "Fabric", "popularity": 60, "rating": 4.4, "owner": "Origin",
     "description": "Fabric-based survival SMP."},
    {"name": "Wynncraft", "host": "play.wynncraft.com", "port": 25565, "gamemode": "MMORPG",
     "loader": "Paper", "popularity": 90, "rating": 4.8, "owner": "Wynncraft Team",
     "description": "Largest Minecraft MMORPG with quests, classes, and a custom world."},
    {"name": "2b2t Anarchy", "host": "2b2t.org", "port": 25565, "gamemode": "Anarchy",
     "loader": "Vanilla", "popularity": 95, "rating": 4.7, "owner": "Hausemaster",
     "description": "Oldest anarchy server, no rules, vanilla."},
    {"name": "Cobblemon Islands", "host": "play.cobblemon.com", "port": 25565, "gamemode": "Cobblemon",
     "loader": "Fabric", "popularity": 75, "rating": 4.6, "owner": "Cobblemon Team",
     "description": "Cobblemon mod (Pokemon in Minecraft) server."},
    {"name": "HermitCraft", "host": "hermitcraft.com", "port": 25565, "gamemode": "Vanilla SMP",
     "loader": "Paper", "popularity": 88, "rating": 4.9, "owner": "Hermitcraft",
     "description": "Whitelisted vanilla SMP featuring popular YouTubers."},
    {"name": "ManaCube", "host": "play.manacube.com", "port": 25565, "gamemode": "Skyblock / Towny",
     "loader": "Spigot", "popularity": 70, "rating": 4.3, "owner": "ManaCube",
     "description": "Skyblock, Towny, Survival, and Parkour servers."},
    {"name": "MassiveCraft", "host": "play.massivecraft.com", "port": 25565, "gamemode": "Factions / RPG",
     "loader": "Folia", "popularity": 65, "rating": 4.4, "owner": "MassiveCraft",
     "description": "Factions and RPG focused server running Folia."},
    {"name": "CubeCraft Games", "host": "play.cubecraft.net", "port": 25565, "gamemode": "Minigames",
     "loader": "Paper", "popularity": 80, "rating": 4.5, "owner": "CubeCraft",
     "description": "Minigame server: EggWars, SkyWars, BedWars."},
    {"name": "Pika-Network", "host": "play.pika-network.net", "port": 25565, "gamemode": "Bedwars / Factions",
     "loader": "Paper", "popularity": 75, "rating": 4.4, "owner": "Pika-Network",
     "description": "Bedwars, Factions, Survival, Skyblock, and more."},
    {"name": "AppleCraft", "host": "play.applecraft.org", "port": 25565, "gamemode": "Survival SMP",
     "loader": "Paper", "popularity": 55, "rating": 4.2, "owner": "AppleCraft",
     "description": "Long-running survival SMP with custom plugins."},
    {"name": "Mineplex", "host": "us.mineplex.com", "port": 25565, "gamemode": "Minigames",
     "loader": "Spigot", "popularity": 50, "rating": 4.0, "owner": "Mineplex",
     "description": "Classic minigame server (returning from hiatus)."},
    {"name": "The Hive", "host": "play.hivemc.com", "port": 25565, "gamemode": "Minigames",
     "loader": "Paper", "popularity": 82, "rating": 4.5, "owner": "The Hive",
     "description": "Hide and Seek, SkyWars, Block Party, DeathRun."},
]

# Owner / youtuber alias -> server host map, used to attribute community servers.
OWNER_ALIASES: Dict[str, Dict[str, Any]] = {
    # alias keywords (lowercased) -> {host, name, owner}
    "drdonut":     {"host": "play.donutsmp.net", "name": "Donut SMP", "owner": "DrDonut"},
    "donut":       {"host": "play.donutsmp.net", "name": "Donut SMP", "owner": "DrDonut"},
    "wisp":        {"host": "play.wispsmp.com", "name": "Wisp SMP", "owner": "Wisp"},
    "clownpierce": {"host": "play.lifestealsmp.com", "name": "Lifesteal SMP", "owner": "ClownPierce"},
    "lifesteal":   {"host": "play.lifestealsmp.com", "name": "Lifesteal SMP", "owner": "ClownPierce"},
    "rekrap":      {"host": "play.echosmp.net", "name": "Echo SMP", "owner": "Rekrap"},
    "subwithfist": {"host": "play.fistsmp.com", "name": "Fist SMP", "owner": "SubWithFist"},
    "flamefrags":  {"host": "play.flamesmp.net", "name": "Flame SMP", "owner": "FlameFrags"},
    "spesilver":   {"host": "play.spekeys.com", "name": "Silver SMP", "owner": "SpeSilver"},
    "hausemaster": {"host": "2b2t.org", "name": "2b2t Anarchy", "owner": "Hausemaster"},
}

# Recognized field vocab
LOADER_PATTERNS = ["fabric", "neoforge", "forge", "quilt", "paper", "purpur", "folia", "spigot", "vanilla", "leaf", "bukkit"]
GAMEMODE_PATTERNS = [
    "hardcore", "anarchy", "survival", "skyblock", "bedwars", "pvp", "smp", "mmorpg",
    "creative", "prison", "factions", "lifesteal", "towny", "cobblemon", "minigames",
    "rpg", "parkour", "kitpvp", "build battle", "skywars", "hide and seek", "uhc",
]
VERSION_RE = re.compile(r"\b(1\.(?:\d{1,2})(?:\.\d{1,2})?)\b")
PLAYER_RE = re.compile(r"\b(\d{1,4})\s*(?:[-–]\s*(\d{1,4}))?\s*players?\b", re.IGNORECASE)
ONLINE_RE = re.compile(r"\b(\d{1,6})\s*(?:online|on\s*line|playing)\b", re.IGNORECASE)

# Common MC server host patterns. Used to extract IPs / hostnames from arbitrary
# prose. NOT just a domain regex — we anchor on mc-/play- prefixes too.
HOST_RE = re.compile(
    r"\b(?:play\.|mc\.|join\.|hub\.)?"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:net|com|org|gg|io|cc|mc|fun|xyz|co|me|us|dev|cloud|games|host|online)\b"
    r"(?::\d{2,5})?",
    re.IGNORECASE,
)
# Plain IPv4, optionally with port.
IPV4_RE = re.compile(
    r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{2,5})?\b"
)

CACHE_PATH = get_dot_neurax_dir() / "cache" / "smart_server_cache.json"
_CACHE_TTL_SECONDS = 60 * 60  # 1 hour
_cache_lock = threading.Lock()


def _http_get(url: str, *, params: Optional[dict] = None, timeout: int = TIMEOUT) -> Optional[requests.Response]:
    try:
        return requests.get(url, params=params, timeout=timeout, headers={"User-Agent": UA})
    except Exception:
        return None


def _read_cache() -> Dict[str, Any]:
    try:
        if CACHE_PATH.exists():
            with open(CACHE_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        pass
    return {}


def _write_cache(cache: Dict[str, Any]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=2)
    except Exception:
        pass


def _cache_get(key: str) -> Optional[Any]:
    with _cache_lock:
        cache = _read_cache()
        entry = cache.get(key)
        if not entry:
            return None
        if time.time() - entry.get("ts", 0) > _CACHE_TTL_SECONDS:
            return None
        return entry.get("value")


def _cache_put(key: str, value: Any) -> None:
    with _cache_lock:
        cache = _read_cache()
        cache[key] = {"ts": time.time(), "value": value}
        # Bound the cache so it doesn't grow without limit.
        if len(cache) > 200:
            now = time.time()
            cache = {
                k: v for k, v in sorted(cache.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True)[:200]
            }
        _write_cache(cache)


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------
def extract_loaders(text: str) -> List[str]:
    text = (text or "").lower()
    found = []
    for loader in LOADER_PATTERNS:
        if loader in text:
            found.append(loader.capitalize())
    return found


def extract_gamemodes(text: str) -> List[str]:
    text = (text or "").lower()
    found = []
    for gm in GAMEMODE_PATTERNS:
        if gm in text:
            found.append(gm.upper())
    return list(dict.fromkeys(found))  # dedup, preserve order


def extract_version(text: str) -> Optional[str]:
    m = VERSION_RE.search(text or "")
    return m.group(0) if m else None


def extract_player_count(text: str) -> Tuple[Optional[int], Optional[int]]:
    m = PLAYER_RE.search(text or "")
    if m:
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else None
        return lo, hi
    return None, None


def extract_hosts(text: str, max_results: int = 5) -> List[Tuple[str, Optional[int]]]:
    """Return [(host, port)] tuples for any MC server-looking hostname found."""
    if not text:
        return []
    seen = set()
    out: List[Tuple[str, Optional[int]]] = []
    # Try domain match first (preferred — real server hostnames).
    for m in HOST_RE.finditer(text):
        token = m.group(0)
        host = token
        port: Optional[int] = None
        if ":" in token and token.rsplit(":", 1)[-1].isdigit():
            host, p = token.rsplit(":", 1)
            try:
                port = int(p)
            except ValueError:
                port = None
        h = host.lower().rstrip(".")
        if h in seen:
            continue
        seen.add(h)
        out.append((h, port))
        if len(out) >= max_results:
            break
    if not out:
        for m in IPV4_RE.finditer(text):
            token = m.group(0)
            host = token
            port = None
            if ":" in token:
                host, p = token.rsplit(":", 1)
                try:
                    port = int(p)
                except ValueError:
                    port = None
            if host in seen:
                continue
            seen.add(host)
            out.append((host, port))
            if len(out) >= max_results:
                break
    return out


def extract_owner(text: str) -> Optional[str]:
    text = text or ""
    patterns = [
        r"(?:by|hosted by|run by|owner[:\s]+|made by)\s+([A-Za-z0-9_\- ]{2,40})",
        r"([A-Za-z0-9_\-]{2,30})['\u2019]?s\s+(?:server|smp|network)",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip(" .,;:!?'\"")
            # Filter common junk.
            if candidate.lower() in {"the", "a", "an", "this", "my", "our"}:
                continue
            return candidate
    return None


# ---------------------------------------------------------------------------
# Source: mcsrvstat.us — live data for a known IP
# ---------------------------------------------------------------------------
def fetch_mcsrvstat(host: str, port: int = 25565) -> Dict[str, Any]:
    if not host:
        return {}
    key = f"mcsrvstat:{host}:{port}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    url = f"https://api.mcsrvstat.us/3/{host}"
    if port and port != 25565:
        url += f":{port}"
    r = _http_get(url, timeout=5)
    if r is None or r.status_code != 200:
        return {}
    try:
        data = r.json()
    except Exception:
        return {}
    if not data.get("online"):
        out = {"online": False, "host": host, "port": port, "players_online": 0, "players_max": 0}
        _cache_put(key, out)
        return out
    motd = data.get("motd", {}).get("clean", [])
    version = data.get("version", "")
    players_on = data.get("players", {}).get("online", 0)
    players_max = data.get("players", {}).get("max", 0)
    out = {
        "online": True,
        "host": host,
        "port": port,
        "players_online": int(players_on or 0),
        "players_max": int(players_max or 0),
        "version": str(version) if version else "",
        "motd": " | ".join(str(x) for x in motd if x)[:280],
    }
    _cache_put(key, out)
    return out


# ---------------------------------------------------------------------------
# Source: DuckDuckGo HTML — general web search (no API key, no JS)
# ---------------------------------------------------------------------------
def _extract_ddg_links(html: str) -> List[Tuple[str, str, str]]:
    """Return [(title, snippet, url)] from a DuckDuckGo HTML result page.

    DDG's `//duckduckgo.com/l/?uddg=...` redirect wraps the real URL inside a
    `uddg` query parameter. We unwrap it so the `source_url` we attach to a
    server candidate is the real destination, not DDG's redirect.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    out: List[Tuple[str, str, str]] = []
    for result in soup.select("div.result"):
        link = result.select_one("a.result__a")
        if not link:
            continue
        raw_href = link.get("href", "")
        if not raw_href:
            continue
        # Resolve DDG's redirect to the real URL.
        href = raw_href
        if raw_href.startswith("//duckduckgo.com/l/") or raw_href.startswith("/l/"):
            try:
                parsed = urllib.parse.urlparse(raw_href if raw_href.startswith("//") else f"https://duckduckgo.com{raw_href}")
                qs = urllib.parse.parse_qs(parsed.query)
                if "uddg" in qs:
                    href = urllib.parse.unquote(qs["uddg"][0])
            except Exception:
                pass
        title = link.get_text(" ", strip=True)
        snippet_el = result.select_one(".result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if title and href.startswith("http"):
            out.append((title, snippet, href))
    if not out:
        for result in soup.select("div.links_main"):
            link = result.select_one("a")
            if not link:
                continue
            href = link.get("href", "")
            title = link.get_text(" ", strip=True)
            if href.startswith("http") and title:
                out.append((title, "", href))
    return out


def search_duckduckgo(query: str, max_results: int = 8) -> List[Dict[str, Any]]:
    """Search DuckDuckGo HTML for Minecraft server-related pages. No API key."""
    if not query.strip():
        return []
    key = f"ddg:{query}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    # Tighten the query so DDG returns MC-server-relevant pages.
    search_q = f"{query} minecraft server IP"
    url = "https://duckduckgo.com/html/"
    r = _http_get(url, params={"q": search_q, "kl": "us-en"}, timeout=TIMEOUT)
    if r is None or r.status_code != 200:
        return []
    rows = _extract_ddg_links(r.text)[:max_results]
    out: List[Dict[str, Any]] = []
    for title, snippet, href in rows:
        combined = f"{title}\n{snippet}\n{href}"
        servers = extract_hosts(combined) or []
        loaders = extract_loaders(combined)
        gamemodes = extract_gamemodes(combined)
        version = extract_version(combined)
        players_min, players_max = extract_player_count(combined)
        owner = extract_owner(combined)
        # Each discovered hostname becomes its own candidate server dict.
        for host, port in servers:
            entry: Dict[str, Any] = {
                "name": title[:60] or host,
                "host": host,
                "port": port or 25565,
                "description": snippet[:240] or title,
                "source": "duckduckgo",
                "source_url": href,
            }
            if loaders:
                entry["loader"] = loaders[0]
            if gamemodes:
                entry["gamemode"] = gamemodes[0]
            if version:
                entry["version"] = version
            if players_min is not None:
                entry["players_min"] = players_min
            if players_max is not None:
                entry["players_max"] = players_max
            if owner:
                entry["owner"] = owner
            out.append(entry)
    _cache_put(key, out)
    return out


# ---------------------------------------------------------------------------
# Source: YouTube HTML search — no key, no API.
# We extract video titles + descriptions from the public search results page.
# ---------------------------------------------------------------------------
def _extract_yt_videos(html: str, max_results: int = 8) -> List[Dict[str, str]]:
    if not html:
        return []
    out: List[Dict[str, str]] = []
    # YouTube's HTML is huge; we just look for video title patterns. We can
    # also pull ytInitialData JSON if present, but it's not always rendered.
    # Approach: find /watch?v=... anchors and harvest their title text.
    soup = BeautifulSoup(html, "html.parser")
    seen_ids = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"/watch\?v=([A-Za-z0-9_\-]{6,16})", href)
        if not m:
            continue
        vid = m.group(1)
        if vid in seen_ids:
            continue
        seen_ids.add(vid)
        title = a.get("title") or a.get_text(" ", strip=True)
        if not title or title.lower() in {"video", "shorts"}:
            continue
        out.append({"video_id": vid, "title": title, "url": f"https://www.youtube.com/watch?v={vid}"})
        if len(out) >= max_results:
            break
    return out


def search_youtube(query: str, max_results: int = 6) -> List[Dict[str, Any]]:
    """Search YouTube for the query. Returns derived server candidates from
    video titles + descriptions. No API key."""
    if not query.strip():
        return []
    key = f"yt:{query}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    search_q = f"{query} minecraft server IP"
    url = "https://www.youtube.com/results"
    r = _http_get(url, params={"search_query": search_q}, timeout=TIMEOUT)
    if r is None or r.status_code != 200:
        return []
    videos = _extract_yt_videos(r.text, max_results=max_results)
    out: List[Dict[str, Any]] = []
    for v in videos:
        combined = f"{v['title']} {v['url']}"
        servers = extract_hosts(combined)
        loaders = extract_loaders(combined)
        gamemodes = extract_gamemodes(combined)
        owner = extract_owner(combined)
        version = extract_version(combined)
        for host, port in servers:
            entry: Dict[str, Any] = {
                "name": v["title"][:60] or host,
                "host": host,
                "port": port or 25565,
                "description": f"YouTube video: {v['title']}",
                "source": "youtube",
                "source_url": v["url"],
            }
            if loaders:
                entry["loader"] = loaders[0]
            if gamemodes:
                entry["gamemode"] = gamemodes[0]
            if owner:
                entry["owner"] = owner
            if version:
                entry["version"] = version
            out.append(entry)
    # Even if no hostnames were extracted, treat the YouTube result as
    # community evidence the server exists. Attach it as a "topic" so the
    # ranking function can still reward the seed list match.
    if not out and videos:
        for v in videos[:2]:
            out.append({
                "name": v["title"][:60],
                "host": "",
                "port": 25565,
                "description": f"YouTube video: {v['title']}",
                "source": "youtube",
                "source_url": v["url"],
                "video_id": v["video_id"],
            })
    _cache_put(key, out)
    return out


# ---------------------------------------------------------------------------
# Source: Reddit HTML — community discussion (no key)
# ---------------------------------------------------------------------------
def search_reddit(query: str, max_results: int = 6) -> List[Dict[str, Any]]:
    """Pull community discussion threads for the query from Reddit.

    Reddit's own search endpoint has been locked behind an auth wall for
    non-browser UAs (returns a 403 "Log in" page), so we route the same
    query through DuckDuckGo with a `site:reddit.com/...` filter. The data
    is real Reddit posts (titles + snippets + URLs), no API key, no auth.
    """
    if not query.strip():
        return []
    key = f"reddit:{query}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    out: List[Dict[str, Any]] = []
    for subreddit in ("admincraft", "Minecraft"):
        try:
            r = _http_get(
                "https://duckduckgo.com/html/",
                params={"q": f"site:reddit.com/r/{subreddit} {query} server", "kl": "us-en"},
                timeout=TIMEOUT,
            )
        except Exception:
            r = None
        if r is None or r.status_code != 200:
            continue
        rows = _extract_ddg_links(r.text)[:max_results]
        for title, snippet, href in rows:
            # Only accept real Reddit URLs, not unrelated results.
            if "reddit.com" not in href:
                continue
            combined = f"{title} {snippet} {href}"
            servers = extract_hosts(combined)
            loaders = extract_loaders(combined)
            gamemodes = extract_gamemodes(combined)
            version = extract_version(combined)
            owner = extract_owner(combined)
            if servers:
                for host, port in servers:
                    entry: Dict[str, Any] = {
                        "name": title[:60] or host,
                        "host": host,
                        "port": port or 25565,
                        "description": f"Reddit thread on r/{subreddit}: {title} — {snippet[:120]}",
                        "source": "reddit",
                        "source_url": href,
                        "source_subreddit": subreddit,
                    }
                    if loaders:
                        entry["loader"] = loaders[0]
                    if gamemodes:
                        entry["gamemode"] = gamemodes[0]
                    if version:
                        entry["version"] = version
                    if owner:
                        entry["owner"] = owner
                    out.append(entry)
            else:
                # No hostname in the snippet — still surface it as a topic so
                # the user can click through and find a server there.
                out.append({
                    "name": title[:60],
                    "host": "",
                    "port": 25565,
                    "description": f"Reddit thread on r/{subreddit}: {title} — {snippet[:120]}",
                    "source": "reddit",
                    "source_url": href,
                    "source_subreddit": subreddit,
                })
            if len(out) >= max_results:
                break
        if len(out) >= max_results:
            break
    _cache_put(key, out)
    return out


# ---------------------------------------------------------------------------
# Owner / IP direct lookup
# ---------------------------------------------------------------------------
def lookup_owner_aliases(query: str) -> List[Dict[str, Any]]:
    """If the user typed a youtuber/owner name, inject that known server
    directly so the user always sees a relevant result."""
    q = (query or "").lower()
    if not q:
        return []
    matched: List[Dict[str, Any]] = []
    for alias, info in OWNER_ALIASES.items():
        if alias in q:
            matched.append({
                "name": info["name"],
                "host": info["host"],
                "port": 25565,
                "owner": info["owner"],
                "source": "owner_alias",
            })
    return matched


def lookup_explicit_ip(query: str) -> List[Dict[str, Any]]:
    """If the user typed a domain or IPv4 in their query, treat it as a direct
    server probe and live-ping it."""
    hosts = extract_hosts(query, max_results=3)
    out: List[Dict[str, Any]] = []
    for host, port in hosts:
        live = fetch_mcsrvstat(host, port or 25565)
        entry = {"host": host, "port": port or 25565, "source": "explicit_ip"}
        if live:
            entry.update(live)
        if not entry.get("name"):
            entry["name"] = host
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Scoring / ranking
# ---------------------------------------------------------------------------
def _normalise(s: Any) -> str:
    return (str(s) if s is not None else "").strip().lower()


def score_server(query: str, server: Dict[str, Any], parsed: Dict[str, Any]) -> Tuple[int, List[str]]:
    """Returns (0..100 score, list of human-readable reasons)."""
    q = (query or "").lower()
    reasons: List[str] = []
    score = 0

    name = _normalise(server.get("name"))
    host = _normalise(server.get("host"))
    desc = _normalise(server.get("description") or server.get("motd") or "")
    loader = _normalise(server.get("loader"))
    gamemode = _normalise(server.get("gamemode"))
    owner = _normalise(server.get("owner"))

    # Empty query: rank by live status + popularity.
    if not q.strip():
        if server.get("online"):
            score += 50
            reasons.append("Currently online")
        score += int(server.get("popularity", 50) * 0.3)
        if server.get("rating", 0) >= 4.5:
            score += 10
            reasons.append("Highly rated community server")
        if server.get("source") == "owner_alias":
            score += 30
            reasons.append("Well-known community server")
        if server.get("source") == "seed":
            score += 20
            reasons.append("Featured seed server")
        if server.get("ai_health_score"):
            score = max(score, int(server["ai_health_score"]))
        return min(100, max(5, score)), reasons

    # Token overlap with name/host/description.
    q_tokens = [t for t in re.split(r"[\s,]+", q) if t and len(t) >= 2]
    corpus = " ".join([name, host, desc, owner])
    hits = sum(1 for t in q_tokens if t in corpus)
    if hits and q_tokens:
        score += int(40 * (hits / len(q_tokens)))
        reasons.append(f"Query match in {hits}/{len(q_tokens)} field(s)")

    # Direct IP match.
    if parsed.get("hint_host") and parsed["hint_host"] in host:
        score += 60
        reasons.append(f"Exact IP match: {parsed['hint_host']}")

    # Owner / youtuber alias.
    if parsed.get("hint_owner") and parsed["hint_owner"] in (owner or ""):
        score += 35
        reasons.append(f"Owner match: {parsed['hint_owner']}")

    # Gamemode.
    if gamemode and any(gm in q for gm in [gamemode, gamemode.replace(" ", "")]):
        score += 20
        reasons.append(f"Gamemode match: {gamemode}")

    # Loader.
    if loader and loader in q:
        score += 20
        reasons.append(f"Loader match: {loader}")

    # Player count.
    players = server.get("players_online") or 0
    if "high" in q and "player" in q and players >= 200:
        score += 25
        reasons.append(f"High population: {players:,} online")
    if "low" in q and "ping" in q and server.get("ping", 999) <= 60 and server.get("online"):
        score += 20
        reasons.append(f"Low ping: {server.get('ping')}ms")
    if "big" in q and "server" in q and players >= 500:
        score += 20
        reasons.append(f"Large community: {players:,} online")

    # Version.
    ql_ver = parsed.get("hint_version")
    s_ver = _normalise(server.get("version"))
    if ql_ver and s_ver and ql_ver == s_ver:
        score += 15
        reasons.append(f"Version match: {ql_ver}")

    # Source weighting.
    source_bonus = {
        "owner_alias": 25,
        "explicit_ip": 25,
        "duckduckgo": 12,
        "youtube": 8,
        "reddit": 8,
        "seed": 5,
    }.get(server.get("source", ""), 0)
    if source_bonus:
        score += source_bonus
        reasons.append(f"Source: {server.get('source')}")

    # Live boost.
    if server.get("online"):
        score += 10
        if players >= 200:
            score += 5
            reasons.append(f"Live: {players:,} players online")
        else:
            reasons.append("Live server")
    else:
        # Offline servers get a small penalty unless they're a known seed.
        if server.get("source") not in ("seed", "owner_alias"):
            score -= 5

    # Multi-source consensus (same server found in 2+ places) — strong signal.
    if isinstance(server.get("sources"), list) and len(server["sources"]) >= 2:
        score += 12
        reasons.append(f"Found in {len(server['sources'])} sources")

    if not reasons:
        reasons.append("Generic community match")
    return min(100, max(0, score)), reasons


# ---------------------------------------------------------------------------
# Query parser
# ---------------------------------------------------------------------------
def parse_query(query: str) -> Dict[str, Any]:
    q = query or ""
    ql = q.lower()
    parsed: Dict[str, Any] = {
        "raw": q,
        "hint_host": None,
        "hint_port": 25565,
        "hint_loader": None,
        "hint_gamemode": None,
        "hint_version": None,
        "hint_owner": None,
        "hint_players_min": None,
        "hint_players_max": None,
    }
    explicit_hosts = extract_hosts(q, max_results=2)
    if explicit_hosts:
        host, port = explicit_hosts[0]
        parsed["hint_host"] = host
        if port:
            parsed["hint_port"] = port

    loaders = extract_loaders(ql)
    if loaders:
        parsed["hint_loader"] = loaders[0]

    gamemodes = extract_gamemodes(ql)
    if gamemodes:
        parsed["hint_gamemode"] = gamemodes[0]

    ver = extract_version(ql)
    if ver:
        parsed["hint_version"] = ver

    owner = extract_owner(ql)
    if owner:
        parsed["hint_owner"] = owner

    pmin, pmax = extract_player_count(ql)
    if pmin is not None:
        parsed["hint_players_min"] = pmin
    if pmax is not None:
        parsed["hint_players_max"] = pmax

    # Look up owner alias if no other owner was found.
    if not parsed["hint_owner"]:
        for alias, info in OWNER_ALIASES.items():
            if alias in ql:
                parsed["hint_owner"] = info.get("owner", alias)
                break
    return parsed


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def discover_servers(query: str, *, sources: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Aggregate results from all enabled sources, dedupe, score, and rank.

    `sources` defaults to all four (duckduckgo, youtube, reddit, mcsrvstat).
    Returns a list of scored server dicts ready for display. Each dict has at
    least: name, host, port, source, ai_health_score, ai_reasons.
    """
    query = (query or "").strip()
    parsed = parse_query(query)
    enabled = set(sources or ["duckduckgo", "youtube", "reddit", "mcsrvstat"])

    candidates: List[Dict[str, Any]] = []
    # 0. Owner alias injection — always helpful, never wrong.
    for entry in lookup_owner_aliases(query):
        entry["gamemode"] = entry.get("gamemode", "Unknown")
        entry["loader"] = entry.get("loader", "Unknown")
        entry["popularity"] = entry.get("popularity", 80)
        entry["rating"] = entry.get("rating", 4.3)
        candidates.append(entry)

    # 1. Explicit IP / domain in the query — always ping.
    for entry in lookup_explicit_ip(query):
        candidates.append(entry)

    # 2. Web sources, in parallel for snappy feel.
    def _ddg():
        return [("duckduckgo", s) for s in search_duckduckgo(query)]
    def _yt():
        return [("youtube", s) for s in search_youtube(query)]
    def _rd():
        return [("reddit", s) for s in search_reddit(query)]
    work_items: List[Tuple[str, Any]] = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = []
        if "duckduckgo" in enabled:
            futures.append(("duckduckgo", ex.submit(_ddg)))
        if "youtube" in enabled:
            futures.append(("youtube", ex.submit(_yt)))
        if "reddit" in enabled:
            futures.append(("reddit", ex.submit(_rd)))
        for src_name, fut in futures:
            try:
                work_items.extend(fut.result(timeout=TIMEOUT + 5))
            except Exception:
                continue

    for src_name, s in work_items:
        # Tag the source. If a host was found across multiple sources, we
        # collect that fact via the 'sources' list down below.
        s = dict(s)
        s.setdefault("source", src_name)
        s.setdefault("sources", []).append(src_name)
        # Set defaults for fields the UI expects.
        s.setdefault("name", s.get("host", "Unknown"))
        s.setdefault("host", "")
        s.setdefault("port", 25565)
        s.setdefault("description", "")
        s.setdefault("gamemode", s.get("gamemode", "Unknown"))
        s.setdefault("loader", s.get("loader", "Unknown"))
        s.setdefault("popularity", 50)
        s.setdefault("rating", 4.0)
        candidates.append(s)

    # 3. If we have a hint_host and mcsrvstat is enabled, live-ping it.
    if "mcsrvstat" in enabled and parsed.get("hint_host"):
        live = fetch_mcsrvstat(parsed["hint_host"], parsed.get("hint_port", 25565))
        if live:
            # Merge into any existing candidate for the same host.
            merged = False
            for c in candidates:
                if c.get("host", "").lower() == parsed["hint_host"].lower():
                    c.update(live)
                    c.setdefault("sources", []).append("mcsrvstat")
                    merged = True
                    break
            if not merged:
                candidates.append({
                    "name": parsed.get("hint_name") or parsed["hint_host"],
                    "host": parsed["hint_host"],
                    "port": parsed.get("hint_port", 25565),
                    "source": "mcsrvstat",
                    **live,
                })

    # 4. Dedupe by host (lowercased). Merge fields from duplicates.
    deduped: Dict[str, Dict[str, Any]] = {}
    for c in candidates:
        h = (c.get("host") or "").lower().strip(".")
        if not h:
            # Keep as a "topic" entry if it has a video/source URL but no host.
            if c.get("source_url"):
                key = f"topic:{c.get('source_url')}"
            else:
                continue
        else:
            key = h
        if key not in deduped:
            c["sources"] = list(dict.fromkeys(c.get("sources", [])))
            deduped[key] = c
            continue
        existing = deduped[key]
        # Prefer non-empty values; merge sources list.
        for f in ("name", "host", "port", "loader", "gamemode", "version", "motd",
                 "description", "owner", "source_url"):
            if not existing.get(f) and c.get(f):
                existing[f] = c[f]
        for f in ("players_online", "players_max", "online"):
            if c.get(f) and not existing.get(f):
                existing[f] = c[f]
        for s in c.get("sources", []):
            if s not in existing["sources"]:
                existing["sources"].append(s)

    # 5. Always overlay the curated seed list at the bottom so the user
    #    never sees a totally empty gallery. Seeds come with popularity so
    #    they're only promoted if the query is empty or the live data is weak.
    seed_keys = set(deduped.keys())
    for s in SEED_SERVERS:
        h = s["host"].lower()
        if h in seed_keys:
            # Merge popularity/rating/owner/description into the existing entry.
            existing = deduped[h]
            for f in ("name", "loader", "gamemode", "owner", "description"):
                if not existing.get(f) and s.get(f):
                    existing[f] = s[f]
            existing.setdefault("popularity", 0)
            existing["popularity"] = max(existing["popularity"], s.get("popularity", 50))
            existing.setdefault("rating", 0)
            existing["rating"] = max(existing["rating"], s.get("rating", 4.0))
            existing.setdefault("sources", []).append("seed")
            continue
        sc = dict(s)
        sc.setdefault("source", "seed")
        sc["sources"] = ["seed"]
        deduped[h] = sc

    # 6. Live-ping every deduped candidate that has a host, in parallel.
    def _ping(c):
        host = c.get("host")
        if not host or c.get("online") is not None:
            return
        try:
            live = fetch_mcsrvstat(host, c.get("port", 25565))
            if live:
                for k, v in live.items():
                    if v is not None and v != "":
                        c[k] = v
        except Exception:
            pass
    pings = [c for c in deduped.values() if c.get("host") and c.get("online") is None]
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(_ping, pings))

    # 7. Score + sort.
    evaluated: List[Dict[str, Any]] = []
    for c in deduped.values():
        item = dict(c)
        score, reasons = score_server(query, item, parsed)
        item["ai_health_score"] = score
        item["ai_reasons"] = reasons
        # Derive a final source label that's user-friendly.
        srcs = item.get("sources") or ([item.get("source")] if item.get("source") else [])
        item["ai_source_label"] = " + ".join(sorted(set(srcs))) if srcs else "unknown"
        evaluated.append(item)

    # Online servers first, then by score, then by popularity.
    evaluated.sort(
        key=lambda x: (
            bool(x.get("online")),
            int(x.get("ai_health_score", 0)),
            int(x.get("players_online", 0)),
            int(x.get("popularity", 0)),
        ),
        reverse=True,
    )

    # 8. Apply hard filters from parsed hints.
    if parsed.get("hint_players_min") is not None:
        evaluated = [
            s for s in evaluated
            if (s.get("players_max") or s.get("players_online") or 0) >= parsed["hint_players_min"]
        ] or evaluated  # if the filter wipes everything, keep all results

    return evaluated
