import re
import math
from typing import List, Dict, Any, Tuple, Set

class AIEngine:
    """Core 0-Token Local Artificial Intelligence & Semantic Processing Engine.
    Operates 100% locally with zero API keys, zero token fees, zero network latency,
    and ultra-low CPU/RAM footprint.
    """

    STOP_WORDS = {
        "a", "an", "the", "in", "on", "at", "for", "to", "of", "with", "by", "from",
        "and", "or", "is", "are", "was", "were", "be", "been", "that", "this", "it",
        "i", "me", "my", "we", "us", "you", "your", "they", "them", "what", "which",
        "find", "give", "show", "get", "minecraft", "server", "servers", "mod", "mods"
    }

    INTENT_KEYWORDS = {
        "server_search": ["server", "smp", "anarchy", "survival", "pvp", "minigames", "skyblock", "bedwars", "hypixel", "donut", "origin", "wynncraft"],
        "mod_search": ["mod", "fabric", "forge", "neoforge", "quilt", "shader", "texture", "resourcepack", "modpack", "optifine", "sodium", "iris"],
        "version_info": ["snapshot", "release", "update", "piston", "beta", "alpha", "indev", "history", "version", "changelog", "1.21", "1.20"],
        "performance": ["ram", "memory", "lag", "fps", "optimize", "stutter", "gc", "jvm", "speed", "boost", "smooth", "crash", "fix"]
    }

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Fast regex tokenization with stopword filtering and lowercase normalization."""
        if not text:
            return []
        raw_tokens = re.findall(r'[a-zA-Z0-9_.-]+', text.lower())
        return [t for t in raw_tokens if len(t) > 1 and t not in AIEngine.STOP_WORDS]

    @staticmethod
    def classify_intent(query: str) -> str:
        """Classify user natural language intent into primary domain."""
        tokens = set(AIEngine.tokenize(query))
        scores = {}
        for intent, kws in AIEngine.INTENT_KEYWORDS.items():
            overlap = len(tokens.intersection(kws))
            scores[intent] = overlap
        
        sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        if sorted_intents and sorted_intents[0][1] > 0:
            return sorted_intents[0][0]
        return "general"

    @staticmethod
    def compute_similarity(query_tokens: List[str], target_corpus: str) -> float:
        """Compute cosine similarity score between query tokens and document corpus."""
        if not query_tokens or not target_corpus:
            return 0.0
        
        doc_tokens = AIEngine.tokenize(target_corpus)
        if not doc_tokens:
            return 0.0

        query_freq = {}
        for t in query_tokens:
            query_freq[t] = query_freq.get(t, 0) + 1

        doc_freq = {}
        for t in doc_tokens:
            doc_freq[t] = doc_freq.get(t, 0) + 1

        common_words = set(query_freq.keys()).intersection(doc_freq.keys())
        if not common_words:
            return 0.0

        dot_product = sum(query_freq[w] * doc_freq[w] for w in common_words)
        query_mag = math.sqrt(sum(v ** 2 for v in query_freq.values()))
        doc_mag = math.sqrt(sum(v ** 2 for v in doc_freq.values()))

        if query_mag * doc_mag == 0:
            return 0.0

        return dot_product / (query_mag * doc_mag)

    @staticmethod
    def extract_key_metrics(text: str) -> Dict[str, Any]:
        """Extract explicit user requirements from natural language input (e.g. RAM, version, loader)."""
        text_l = text.lower()
        metrics = {
            "ram_mb": None,
            "version": None,
            "loader": None,
            "tags": []
        }

        # RAM extraction (e.g. "8gb", "4096mb")
        ram_gb_match = re.search(r'(\d+)\s*(?:gb|g)\b', text_l)
        if ram_gb_match:
            metrics["ram_mb"] = int(ram_gb_match.group(1)) * 1024
        else:
            ram_mb_match = re.search(r'(\d+)\s*(?:mb|m)\b', text_l)
            if ram_mb_match:
                metrics["ram_mb"] = int(ram_mb_match.group(1))

        # Version extraction (e.g. "1.20.4", "1.21.1", "1.8.9")
        ver_match = re.search(r'\b(1\.\d+(?:\.\d+)?)\b', text_l)
        if ver_match:
            metrics["version"] = ver_match.group(1)

        # Loader extraction
        for loader in ["fabric", "neoforge", "forge", "quilt", "paper", "purpur", "folia", "leaf", "vanilla"]:
            if loader in text_l:
                metrics["loader"] = loader.capitalize()
                break

        # Tags extraction
        if "hardcore" in text_l:
            metrics["tags"].append("Hardcore")
        if "anarchy" in text_l:
            metrics["tags"].append("Anarchy")
        if "pvp" in text_l:
            metrics["tags"].append("PvP")
        if "smp" in text_l:
            metrics["tags"].append("SMP")
        if "survival" in text_l:
            metrics["tags"].append("Survival")
        if "creative" in text_l:
            metrics["tags"].append("Creative")
        if "low ping" in text_l or "fast" in text_l:
            metrics["tags"].append("LowPing")
        if "popular" in text_l or "high player" in text_l:
            metrics["tags"].append("HighPop")

        return metrics
