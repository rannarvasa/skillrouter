import os
import sys
import yaml
from pathlib import Path
from typing import Optional

from matcher import build_matcher


STRENGTH_ORDER = ["tiny", "small", "strong", "frontier"]


def strength_rank(s: str) -> int:
    try:
        return STRENGTH_ORDER.index(s)
    except ValueError:
        return 1


class Skill:
    def __init__(self, path: Path, data: dict):
        self.path = path
        self.name = data["name"]
        self.description = data.get("description", "")
        self.triggers = [t.lower() for t in data.get("triggers", [])]
        self.kind = data.get("kind")
        self.strength = data.get("strength")
        self.privacy = data.get("privacy", "any")
        self.provider_preference = data.get("provider_preference", "local_first")
        self.model = data.get("model")
        self.provider = data.get("provider")
        self.system_prompt = data.get("system_prompt", "")
        self.tool = data.get("tool")

        if not self.model and not (self.kind and self.strength):
            raise ValueError(
                f"Skill '{self.name}': must declare either 'model' (explicit override) "
                f"or ('kind' and 'strength')."
            )
        if self.privacy == "local_only" and self.provider == "anthropic":
            raise ValueError(
                f"Skill '{self.name}' has privacy=local_only but provider=anthropic."
            )

    def match_score(self, prompt: str) -> int:
        p = prompt.lower()
        return sum(len(t) for t in self.triggers if t in p)


class ModelRegistry:
    """Classifies installed Ollama tags + known Anthropic models by (kind, strength)."""

    def __init__(self, config: dict, ollama_host: str):
        self.rules = config.get("model_rules", [])
        self.anthropic_models = config.get("anthropic_models", {})
        self.default_fallback_kind = config.get("default_fallback_kind", "general")
        self.ollama_error: Optional[str] = None
        self.installed_ollama: list[dict] = self._scan_ollama(ollama_host)
        self.api_available = bool(os.environ.get(
            config.get("providers", {}).get("anthropic", {}).get("api_key_env", "ANTHROPIC_API_KEY")
        ))

    def _scan_ollama(self, host: str) -> list[dict]:
        """Return list of {tag, kinds, strength} for every installed Ollama model."""
        try:
            import ollama
            client = ollama.Client(host=host)
            resp = client.list()
            tags = []
            for m in resp.get("models", []):
                tag = m.get("model") or m.get("name")
                if tag:
                    tags.append(tag)
        except Exception as e:
            self.ollama_error = str(e)
            return []

        classified = []
        for tag in tags:
            kinds, strength = self._classify(tag)
            classified.append({"tag": tag, "kinds": kinds, "strength": strength})
        return classified

    def _classify(self, tag: str) -> tuple[list[str], str]:
        t = tag.lower()
        for rule in self.rules:
            if rule["match"].lower() in t:
                kinds = rule.get("kinds", ["general"])
                strength = rule.get("strength", "small")
                size_map = rule.get("strength_by_size", {}) or {}
                for size, st in size_map.items():
                    if size.lower() in t:
                        strength = st
                        break
                return kinds, strength
        return ([self.default_fallback_kind], "small")

    def candidates(self, kind: str, privacy: str) -> list[dict]:
        """Return all models that can handle `kind`, respecting privacy."""
        out = []
        for m in self.installed_ollama:
            if kind in m["kinds"]:
                out.append({
                    "tag": m["tag"],
                    "provider": "ollama",
                    "strength": m["strength"],
                })
        if privacy != "local_only" and self.api_available:
            for tag, meta in self.anthropic_models.items():
                if kind in meta.get("kinds", []):
                    out.append({
                        "tag": tag,
                        "provider": "anthropic",
                        "strength": meta.get("strength", "frontier"),
                    })
        return out

    def pick(
        self,
        kind: str,
        target_strength: str,
        privacy: str,
        provider_preference: str,
        local_only: bool,
    ) -> Optional[dict]:
        """Rank candidates by strength distance to target, then provider preference."""
        cands = self.candidates(kind, privacy)
        if local_only:
            cands = [c for c in cands if c["provider"] == "ollama"]
        if not cands:
            return None

        target = strength_rank(target_strength)

        def prov_bonus(c):
            if provider_preference == "api_first":
                return 0 if c["provider"] == "anthropic" else 1
            return 0 if c["provider"] == "ollama" else 1

        def key(c):
            diff = strength_rank(c["strength"]) - target
            # Prefer exact match; then higher-strength (nicer); then lower; then provider pref.
            return (abs(diff), 0 if diff >= 0 else 1, prov_bonus(c), c["tag"])

        cands.sort(key=key)
        return cands[0]


class Router:
    def __init__(self, root: Path):
        self.root = root
        self.config = self._load_config(root / "config.yaml")
        self.skills = self._load_skills(root / "skills")
        ollama_host = self.config["providers"]["ollama"]["host"]
        self.registry = ModelRegistry(self.config, ollama_host)
        self._validate_default_model()
        self.matcher = build_matcher(self.skills, self.config, root)

    def _validate_default_model(self):
        """If config's default_model isn't installed, auto-pick the smallest installed Ollama tag."""
        configured = self.config.get("default_model")
        installed_tags = [m["tag"] for m in self.registry.installed_ollama]
        if configured in installed_tags:
            return
        if not installed_tags:
            return  # nothing to fall back to; let callers error with a clear message later

        strength_order = {"tiny": 0, "small": 1, "strong": 2, "frontier": 3}
        non_embed = [
            m for m in self.registry.installed_ollama
            if "embed" not in m["tag"].lower() and "general" in m["kinds"]
        ] or self.registry.installed_ollama
        non_embed.sort(key=lambda m: (strength_order.get(m["strength"], 1), m["tag"]))
        pick = non_embed[0]["tag"]

        if configured:
            print(
                f"[router] default_model '{configured}' is not installed. "
                f"Using '{pick}' instead (auto-picked from installed models).",
                file=sys.stderr,
            )
        self.config["default_model"] = pick

    def _load_config(self, path: Path) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_skills(self, skills_dir: Path) -> list[Skill]:
        skills = []
        for p in sorted(skills_dir.glob("*.yaml")):
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            skills.append(Skill(p, data))
        return skills

    def find_skill(self, name: str) -> Optional[Skill]:
        for s in self.skills:
            if s.name == name:
                return s
        return None

    def match(self, prompt: str) -> Optional[Skill]:
        skill, _ = self.matcher.match(prompt)
        return skill

    def pricing(self, provider: str, model: str) -> Optional[dict]:
        """Return {input, output} USD-per-million-token prices, or None if unpriced."""
        if provider == "anthropic":
            meta = self.config.get("anthropic_models", {}).get(model, {})
            if "price_per_mtok_input" in meta:
                return {
                    "input": meta["price_per_mtok_input"],
                    "output": meta["price_per_mtok_output"],
                }
        return None

    def resolve_for_skill(self, skill: Skill, local_forced: bool) -> dict:
        """Return {provider, model, reason} for a given skill."""
        # Explicit override path — honor exactly, respect --local.
        if skill.model and skill.provider:
            provider = skill.provider
            model = skill.model
            reason = "explicit_override"
            if local_forced and provider != "ollama":
                provider = "ollama"
                model = self.config["default_model"]
                reason = "local_forced"
                print(
                    f"[router] warning: skill '{skill.name}' wants {skill.provider}, "
                    f"but --local forced. Using {model}."
                )
            return {"provider": provider, "model": model, "reason": reason}

        # Capability-driven pick.
        pick = self.registry.pick(
            kind=skill.kind,
            target_strength=skill.strength,
            privacy=skill.privacy,
            provider_preference=skill.provider_preference,
            local_only=local_forced or skill.privacy == "local_only",
        )

        if pick:
            reason = "capability_match"
            if pick["provider"] == "anthropic" and not any(
                m["tag"] == pick["tag"] for m in self.registry.installed_ollama
            ):
                if not any(c["provider"] == "ollama" for c in
                           self.registry.candidates(skill.kind, skill.privacy)):
                    reason = "anthropic_fallback"
            if local_forced:
                reason = "local_forced"
            return {"provider": pick["provider"], "model": pick["tag"], "reason": reason}

        # Nothing matched — helpful error.
        hint = self._pull_hint(skill.kind, skill.strength)
        raise RuntimeError(
            f"No installed model can handle kind='{skill.kind}' for skill "
            f"'{skill.name}'. {hint}"
        )

    def _pull_hint(self, kind: str, strength: str) -> str:
        suggestions = {
            ("coding", "strong"): "ollama pull qwen2.5-coder:7b",
            ("coding", "frontier"): "ollama pull qwen2.5-coder:32b",
            ("summarization", "small"): "ollama pull qwen2.5:3b",
            ("rewriting", "small"): "ollama pull qwen2.5:3b",
            ("reasoning", "frontier"): "set ANTHROPIC_API_KEY to use Claude",
            ("general", "small"): "ollama pull qwen2.5:3b",
        }
        sug = suggestions.get((kind, strength), "ollama pull qwen2.5:3b")
        return f"Try: {sug}"

    def resolve(
        self,
        prompt: str,
        forced_skill: Optional[str] = None,
        local_forced: bool = False,
    ) -> dict:
        skill: Optional[Skill] = None
        if forced_skill:
            skill = self.find_skill(forced_skill)
            if not skill:
                raise ValueError(f"No skill named '{forced_skill}'")
        if not skill:
            skill = self.match(prompt)

        if not skill:
            return {
                "skill": None,
                "provider": "ollama",
                "model": self.config["default_model"],
                "system_prompt": "You are a helpful assistant.",
                "reason": "default_fallback",
            }

        pick = self.resolve_for_skill(skill, local_forced)
        return {
            "skill": skill.name,
            "provider": pick["provider"],
            "model": pick["model"],
            "system_prompt": skill.system_prompt,
            "reason": pick["reason"],
            "tool": skill.tool,
        }

    def make_provider(self, provider_name: str):
        if provider_name == "ollama":
            from providers.ollama_provider import OllamaProvider
            return OllamaProvider(host=self.config["providers"]["ollama"]["host"])
        if provider_name == "anthropic":
            from providers.anthropic_provider import AnthropicProvider
            return AnthropicProvider(
                api_key_env=self.config["providers"]["anthropic"]["api_key_env"]
            )
        raise ValueError(f"Unknown provider: {provider_name}")
