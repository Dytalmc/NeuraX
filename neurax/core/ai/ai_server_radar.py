"""
ai_server_radar.py - Enhanced AI Server Radar with Smart Web Search
====================================================================
This module is the compatibility shim that the existing UI talks to. The
heavy lifting now happens in `neurax.core.ai.smart_server_discovery`, which
aggregates from mcsrvstat.us, DuckDuckGo HTML, YouTube HTML, and Reddit HTML
— all without any API keys, tokens, or LLMs.

We preserve the public symbols (AIServerRadar, AIServerSearchWorker,
SmartServerParser, WebServerSearchEngine) so no GUI changes are required.
"""
import re
import time
import threading
import requests
from urllib.parse import quote_plus
from typing import List, Dict, Any, Tuple, Optional
from PyQt6.QtCore import QThread, pyqtSignal
from neurax.core.ai.ai_engine import AIEngine
from neurax.core.logger import Logger

# The new multi-source discovery engine.
from neurax.core.ai.smart_server_discovery import (  # noqa: F401
    discover_servers,
    parse_query,
    extract_loaders,
    extract_gamemodes,
    extract_version,
    extract_player_count,
    extract_hosts,
    extract_owner,
    fetch_mcsrvstat,
    SEED_SERVERS,
    OWNER_ALIASES,
)


class SmartServerParser:
    """Extracts structured server data from natural language descriptions.

    Backwards-compatible wrapper around the new extraction functions in
    `smart_server_discovery`. The old 21-row `YOUTUBER_TO_SERVER` is kept
    as a deprecated alias for code that referenced it directly.
    """

    YOUTUBER_TO_SERVER: Dict[str, Dict] = {
        key: {
            "name": info["name"],
            "host": info["host"],
            "port": 25565,
            "loader": "Unknown",
            "gamemode": "Unknown",
        }
        for key, info in OWNER_ALIASES.items()
    }

    IP_PATTERN = re.compile(
        r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+(?:net|com|org|gg|io|cc|mc|fun|xyz|co|me)\b'
        r'(?::\d{1,5})?'
    )

    @classmethod
    def extract_from_description(cls, description: str) -> Dict[str, Any]:
        parsed = parse_query(description or "")
        result: Dict[str, Any] = {
            "hint_name": None,
            "hint_host": parsed.get("hint_host"),
            "hint_port": parsed.get("hint_port", 25565),
            "hint_loader": parsed.get("hint_loader"),
            "hint_gamemode": parsed.get("hint_gamemode"),
            "hint_youtuber": None,
            "hint_owner": parsed.get("hint_owner"),
            "hint_version": parsed.get("hint_version"),
            "direct_servers": [],
        }
        desc_lower = (description or "").lower()
        for key, info in OWNER_ALIASES.items():
            if key in desc_lower:
                result["hint_youtuber"] = key
                result["hint_name"] = info["name"]
                result["direct_servers"].append({
                    "name": info["name"],
                    "host": info["host"],
                    "port": 25565,
                    "owner": info.get("owner"),
                })
                break
        return result


class WebServerSearchEngine:
    """Queries DuckDuckGo HTML + YouTube HTML + Reddit HTML + mcsrvstat.us
    for real server discovery. Zero API keys, zero tokens, zero LLM.

    The actual scraping/extraction lives in `smart_server_discovery`. This
    class is a backwards-compatible facade used by `AIServerSearchWorker`
    and the rest of the UI.
    """
    DDGO_URL = "https://api.duckduckgo.com/"
    MCAPI_URL = "https://api.mcsrvstat.us/3/{host}"

    @classmethod
    def search_server(cls, query: str, timeout: int = 8) -> List[Dict[str, Any]]:
        """Return web-discovered server candidates for the query.

        Aggregates from DuckDuckGo HTML, YouTube HTML, and Reddit HTML. Each
        entry is a dict with at minimum: name, host, port, source.
        """
        from neurax.core.ai.smart_server_discovery import (
            search_duckduckgo, search_youtube, search_reddit,
        )
        out: List[Dict[str, Any]] = []
        seen_hosts = set()
        for src_fn in (search_duckduckgo, search_youtube, search_reddit):
            try:
                rows = src_fn(query) or []
            except Exception:
                rows = []
            for r in rows:
                h = (r.get("host") or "").lower()
                if h and h in seen_hosts:
                    continue
                if h:
                    seen_hosts.add(h)
                out.append(r)
        return out

    @classmethod
    def ping_server(cls, host: str, port: int = 25565, timeout: int = 5) -> Dict[str, Any]:
        """Live-ping a known host via mcsrvstat.us. Returns an empty dict on
        network failure, or a populated dict with online/players_online/etc."""
        return fetch_mcsrvstat(host, port)


class AIServerRadar:
    """
    Enhanced AI Server Monitoring & Discovery Engine.
    Local semantic scoring + DuckDuckGo web search + mcsrvstat.us pinging.
    No API key required. Zero-token. Zero cost.
    """

    @staticmethod
    def calculate_health_score(server_data: Dict[str, Any]) -> int:
        if not server_data.get("online", False):
            return 0
        ping = server_data.get("ping", 999)
        players = server_data.get("players_online", 0)
        popularity = server_data.get("popularity", 50)
        rating = server_data.get("rating", 4.0)

        if ping < 0:
            ping_score = 0
        elif ping <= 35:
            ping_score = 40
        elif ping <= 80:
            ping_score = 35 - int((ping - 35) * 0.2)
        elif ping <= 180:
            ping_score = 25 - int((ping - 80) * 0.15)
        else:
            ping_score = max(5, int(300 - ping) // 20)

        if players >= 1000:
            player_score = 30
        elif players >= 200:
            player_score = 25
        elif players >= 50:
            player_score = 20
        elif players >= 10:
            player_score = 15
        else:
            player_score = 10

        rating_score = int(min(5.0, max(1.0, rating)) * 4)
        pop_score = int(min(100, max(0, popularity)) * 0.1)
        return min(100, max(15, ping_score + player_score + rating_score + pop_score))

    @staticmethod
    def evaluate_server_match(query: str, server: Dict[str, Any], parsed: Dict[str, Any] = None) -> Tuple[int, List[str]]:
        if not query.strip():
            return AIServerRadar.calculate_health_score(server), ["Verified High-Reliability Market Server"]

        query_tokens = AIEngine.tokenize(query)
        extracted = AIEngine.extract_key_metrics(query)
        parsed = parsed or SmartServerParser.extract_from_description(query)

        corpus = (
            f"{server.get('name', '')} {server.get('host', '')} "
            f"{server.get('gamemode', '')} {server.get('loader', '')} "
            f"{server.get('description', '')} {server.get('motd', '')}"
        )
        sim_score = AIEngine.compute_similarity(query_tokens, corpus)
        score = int(sim_score * 70)
        reasons: List[str] = []

        if parsed.get("hint_host") and parsed["hint_host"].lower() in server.get("host", "").lower():
            score += 50
            reasons.append(f"Direct IP Match: {parsed['hint_host']}")

        if parsed.get("hint_youtuber") and parsed["hint_youtuber"].lower() in corpus.lower():
            score += 40
            reasons.append("YouTuber/Owner Associated Server")

        if extracted.get("loader") and extracted["loader"].lower() in str(server.get("loader", "")).lower():
            score += 25
            reasons.append(f"Matching {extracted['loader']} Architecture")

        if parsed.get("hint_gamemode"):
            gm = parsed["hint_gamemode"].lower()
            if gm in corpus.lower():
                score += 20
                reasons.append(f"Matching {parsed['hint_gamemode']} Gamemode")

        for tag in extracted.get("tags", []):
            if tag == "LowPing" and server.get("ping", 999) <= 60 and server.get("online"):
                score += 20
                reasons.append(f"Ultra-Low Latency ({server.get('ping')}ms)")
            elif tag == "HighPop" and server.get("players_online", 0) >= 500:
                score += 20
                reasons.append(f"High Active Population ({server.get('players_online'):,} online)")
            elif tag.lower() in corpus.lower():
                score += 15
                reasons.append(f"Verified {tag} Gameplay")

        base_health = AIServerRadar.calculate_health_score(server)
        final_score = min(100, max(0, int(score * 0.65 + base_health * 0.35)))

        if not reasons:
            reasons.append("High Performance & Uptime Match" if final_score > 70 else "Relevant Semantic Discovery")

        return final_score, reasons

    @staticmethod
    def generate_ai_summary(servers: List[Dict[str, Any]], query: str = "") -> Dict[str, Any]:
        online_count = sum(1 for s in servers if s.get("online"))
        total_players = sum(s.get("players_online", 0) for s in servers if s.get("online"))
        pings = [s.get("ping", 0) for s in servers if s.get("online") and s.get("ping", 0) > 0]
        avg_ping = int(sum(pings) / max(1, len(pings)))
        top_server = max(servers, key=lambda x: x.get("ai_health_score", 0)) if servers else None
        top_name = top_server.get("name", "N/A") if top_server else "N/A"

        if query:
            summary = (
                f"AI analysed {len(servers)} servers for '{query}'. "
                f"{online_count} online with {total_players:,} active players. "
                f"Top match: {top_name}."
            )
        else:
            summary = (
                f"Monitoring {len(servers)} servers. "
                f"{online_count} online ({total_players:,} players, {avg_ping}ms avg). "
                f"Top cluster: {top_name}."
            )
        return {
            "summary": summary,
            "online_count": online_count,
            "total_players": total_players,
            "avg_ping": avg_ping,
            "top_server": top_name
        }


class AIServerSearchWorker(QThread):
    """
    Background AI search worker:
    1. Parse natural language with SmartServerParser
    2. Score known servers + add youtuber-matched servers
    3. Web-search DuckDuckGo for IPs if description mentions unknown server
    4. Live-ping discovered servers via mcsrvstat.us
    5. Emit ranked, scored results
    """
    results_ready = pyqtSignal(list, dict)
    search_status = pyqtSignal(str)

    def __init__(self, query: str, servers: List[Dict[str, Any]], enable_web_search: bool = True):
        super().__init__()
        self.query = query
        self.servers = list(servers)
        self.enable_web_search = enable_web_search
        self.logger = Logger.get_instance()

    def run(self):
        try:
            query = (self.query or "").strip()
            parsed = SmartServerParser.extract_from_description(query)
            self.search_status.emit("Parsing query and selecting sources...")

            # Always merge any user-provided server data the GUI was tracking
            # (e.g. the current view's known servers) so the user never loses
            # context — they get the union of cached + freshly discovered.
            baseline = list(self.servers or [])
            baseline_hosts = {s.get("host", "").lower() for s in baseline if s.get("host")}

            discovered: List[Dict[str, Any]] = []
            if self.enable_web_search:
                self.search_status.emit("Searching DuckDuckGo, YouTube, and Reddit...")
                try:
                    discovered = discover_servers(query)
                except Exception as ex:
                    self.logger.warning(f"[AIServerRadar] discover_servers error: {ex}")
                    discovered = []
            else:
                # Web search disabled: still inject any explicit IP or owner
                # alias matches from the parser so the user gets *some* result.
                from neurax.core.ai.smart_server_discovery import (
                    lookup_owner_aliases, lookup_explicit_ip,
                )
                for entry in lookup_owner_aliases(query):
                    discovered.append({**entry, "source": "owner_alias",
                                       "sources": ["owner_alias"]})
                for entry in lookup_explicit_ip(query):
                    discovered.append({**entry, "source": "explicit_ip",
                                       "sources": ["explicit_ip"]})

            # Merge baseline (GUI cache) so any servers the user already
            # sees in the browser don't disappear after a search.
            merged: Dict[str, Dict[str, Any]] = {}
            for s in discovered:
                h = (s.get("host") or "").lower()
                key = h or f"topic:{s.get('source_url') or s.get('name')}"
                if key not in merged:
                    merged[key] = s
                else:
                    cur = merged[key]
                    for f in ("name", "host", "loader", "gamemode", "version", "motd",
                             "description", "owner"):
                        if not cur.get(f) and s.get(f):
                            cur[f] = s[f]
                    for sname in (s.get("sources") or []):
                        if sname not in cur.setdefault("sources", []):
                            cur["sources"].append(sname)
            for s in baseline:
                h = (s.get("host") or "").lower()
                if not h:
                    continue
                if h not in merged:
                    merged[h] = s
                else:
                    cur = merged[h]
                    for f in ("name", "host", "loader", "gamemode", "version", "motd",
                             "description", "owner"):
                        if not cur.get(f) and s.get(f):
                            cur[f] = s[f]

            self.search_status.emit("Ranking and scoring results...")
            evaluated: List[Dict[str, Any]] = []
            for s in merged.values():
                item = dict(s)
                score, reasons = AIServerRadar.evaluate_server_match(query, item, parsed)
                item["ai_health_score"] = score
                item["ai_reasons"] = reasons
                evaluated.append(item)

            evaluated.sort(key=lambda x: (
                bool(x.get("online")),
                int(x.get("ai_health_score", 0)),
                int(x.get("players_online", 0)),
                int(x.get("popularity", 0)),
            ), reverse=True)

            insights = AIServerRadar.generate_ai_summary(evaluated, query)
            if evaluated:
                top = evaluated[0]
                sources_used = sorted({
                    s for it in evaluated for s in (it.get("sources") or [it.get("source")] or [])
                    if s
                })
                src_label = ", ".join(s for s in sources_used if s) or "cache"
                insights["summary"] = (
                    f"Searched {src_label} for '{query}'. "
                    f"{insights.get('online_count', 0)} online, "
                    f"{insights.get('total_players', 0):,} players, "
                    f"top match: {top.get('name', 'N/A')}."
                )
            self.results_ready.emit(evaluated, insights)

        except Exception as e:
            self.logger.error(f"AIServerSearchWorker error: {e}")
            fallback = [dict(s, ai_health_score=0, ai_reasons=["Search error"]) for s in self.servers]
            self.results_ready.emit(fallback, {
                "summary": "Search encountered an error. Showing cached servers.",
                "online_count": 0, "total_players": 0, "avg_ping": 0, "top_server": "N/A"
            })
