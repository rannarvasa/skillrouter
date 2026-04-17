"""Prompt-to-skill matching. Keyword (fast, zero-dep) and embedding (semantic, via Ollama)."""
import hashlib
import json
import math
from pathlib import Path
from typing import Optional


class KeywordMatcher:
    def __init__(self, skills):
        self.skills = skills

    def match(self, prompt: str):
        best = None
        best_score = 0
        for s in self.skills:
            score = s.match_score(prompt)
            if score > best_score:
                best_score = score
                best = s
        return best, best_score


class EmbeddingMatcher:
    """Semantic skill matching via Ollama embeddings. Caches skill vectors on disk."""

    def __init__(self, skills, host: str, model: str, threshold: float, cache_dir: Path):
        self.skills = skills
        self.host = host
        self.model = model
        self.threshold = threshold
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        self._client = None
        self._skill_vectors = None

    def _ollama(self):
        if self._client is None:
            import ollama
            self._client = ollama.Client(host=self.host)
        return self._client

    def _embed(self, text: str) -> list[float]:
        try:
            resp = self._ollama().embeddings(model=self.model, prompt=text)
        except Exception as e:
            raise RuntimeError(
                f"embedding call failed ({e}). Pull the model: "
                f"`ollama pull {self.model}` or switch matching.method to keyword in config.yaml."
            )
        return list(resp["embedding"])

    def _skill_text(self, skill) -> str:
        triggers = " ".join(skill.triggers)
        return f"{skill.description}. Examples: {triggers}"

    def _load_skill_vectors(self):
        if self._skill_vectors is not None:
            return self._skill_vectors

        texts = [self._skill_text(s) for s in self.skills]
        fingerprint = hashlib.sha256(
            (self.model + "|" + "|".join(s.name + ":" + t for s, t in zip(self.skills, texts))).encode()
        ).hexdigest()[:16]
        cache_path = self.cache_dir / f"skill_vectors_{fingerprint}.json"

        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                self._skill_vectors = json.load(f)
            return self._skill_vectors

        vectors = {}
        for skill, text in zip(self.skills, texts):
            vectors[skill.name] = self._embed(text)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(vectors, f)
        self._skill_vectors = vectors
        return vectors

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def match(self, prompt: str):
        vectors = self._load_skill_vectors()
        prompt_vec = self._embed(prompt)
        best = None
        best_score = 0.0
        for skill in self.skills:
            v = vectors.get(skill.name)
            if not v:
                continue
            score = self._cosine(prompt_vec, v)
            if score > best_score:
                best_score = score
                best = skill
        if best_score < self.threshold:
            return None, best_score
        return best, best_score


def build_matcher(skills, config: dict, root: Path):
    matching = config.get("matching", {}) or {}
    method = matching.get("method", "keyword")
    if method == "embedding":
        host = config["providers"]["ollama"]["host"]
        model = matching.get("embed_model", "nomic-embed-text")
        threshold = float(matching.get("threshold", 0.55))
        cache_dir = root / ".cache"
        return EmbeddingMatcher(skills, host, model, threshold, cache_dir)
    return KeywordMatcher(skills)
