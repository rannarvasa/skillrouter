# Changelog

## v0.3.0 — 2026-04-18

### Added
- **Web access for local models.** New `tool: web` field on skills. When a skill declares it, the router runs a DuckDuckGo search + page fetch on the prompt and injects the results as context before calling the model. No API keys, no new Python deps — pure stdlib (`urllib`, `html.parser`).
- **New `web_search` skill** — triggers on "news", "latest", "today", "current", "price of", "weather", etc. Just type a question that needs live info and the local model gets fresh web context automatically.
- **New `skillrouter/tools/` package** — pluggable place for future tools (file reading, shell exec, etc.).

### Example
```bash
$ ask "whats the latest news on Anthropic Claude"
[router] skill: web_search | model: gemma4-memory
[tool] searching the web... fetched 13413 chars
The latest news centers on Claude Opus 4.7, released...
```

## v0.2.0 — 2026-04-18

### Added
- **Embedding-based skill matching** via Ollama embeddings. Set `matching.method: embedding` in `config.yaml` and run `ollama pull nomic-embed-text`. Matches prompts to skills semantically instead of by keyword. Skill vectors are cached to `.cache/` on first run.
- **Cost tracking** for Anthropic calls. Prices defined per-model in `config.yaml`. Every call logs `input_tokens`, `output_tokens`, and `cost_usd` to the monthly JSONL.
- **`--cost` flag** shows this month's API spend, broken down by model.
- **Ollama token counts** are now logged too (from `prompt_eval_count` / `eval_count`).

### Changed
- Providers now return `{text, input_tokens, output_tokens}` instead of a bare string. This is a breaking change for anyone who had a custom provider.
- Ollama errors are now friendly: connection-refused says "is Ollama running?", missing-model says which `ollama pull` command to run.

### Fixed
- Matching logic moved into a dedicated `matcher.py` module. Easier to swap strategies.

## v0.1.0 — 2026-04-17

Initial release.

- Keyword-based matching
- Ollama + Anthropic providers
- Capability-driven model selection (kind + strength + privacy)
- Explicit skill and model overrides
- JSONL logging
- `--doctor`, `--list-skills`, `--skill`, `--local` flags
