# skillrouter

> Route prompts to the right LLM — local Ollama by default, Anthropic API only when it matters.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Good First Issues](https://img.shields.io/github/issues/rannarvasa/skillrouter/good%20first%20issue.svg)](https://github.com/rannarvasa/skillrouter/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)

A local-first CLI that routes prompts to the right LLM — local Ollama models or the Anthropic API — based on a library of **skill files**. Match capability to task. Keep cheap things local. Only escalate to a frontier model when the task actually needs it.

```bash
$ ask "write a function to reverse a string"
[router] skill: python_function | provider: ollama | model: qwen2.5-coder:7b

def reverse_string(s: str) -> str:
    """Return the reverse of the given string."""
    return s[::-1]
```

**New here?** Jump to [Installation](#installation) → [Usage](#usage) → [Adding new skills](#adding-new-skills).
**Want to contribute?** See [CONTRIBUTING.md](CONTRIBUTING.md) — adding a skill is a single YAML file.

---

## Why this exists

Most LLM tools give you one model. You either pay per token for a frontier API (smart but expensive, online, data leaves your machine) or run a local model (free, private, offline, but limited). The reality is that **most prompts don't need a frontier model**. Autocomplete, summarization, rewriting, simple code — a 7B local model handles these fine. You only need the big guns for real reasoning, planning, and novel problems.

skillrouter lets you:

- Default to local models via Ollama (free, private, fast)
- Escalate to the Anthropic API only when a task genuinely requires it
- Define your own "skills" — reusable task templates that declare which model can handle them
- Enforce privacy: some skills never leave your machine, period
- Build up a personal library of automations over time

Think of it as a smart dispatcher for your own AI setup.

---

## Core concepts

### Skills

A **skill** is a YAML file describing a task. It contains:

- A description of what the skill is for
- Trigger keywords that match incoming prompts
- The provider and model best suited for the task
- A system prompt that tells the model how to do the task
- A privacy tier (any / local_only)

Skills do double duty: they tell the model *how* to do the task, and they tell the router *which* model to pick.

### Router

The **router** is the core logic. It:

1. Loads all skills from the `skills/` directory
2. Matches an incoming prompt against skill triggers
3. Picks the skill with the best match
4. Dispatches the prompt + skill's system prompt to the chosen provider/model
5. Streams the response back

If no skill matches, it falls back to a configured default model.

### Providers

Two providers are supported out of the box:

- **Ollama** — local models running on your machine (free, private, offline)
- **Anthropic** — Claude models via API (smart, costs money, requires internet)

Each skill picks one. Extensible to more providers (OpenAI, Gemini, etc.) with minor code additions.

---

## Project structure

```
skillrouter/
  cli.py                      # entry point, argument parsing, logging
  router.py                   # skill loading, matching, dispatch logic
  config.yaml                 # global settings, default model, API keys
  requirements.txt            # Python dependencies
  README.md                   # this file
  providers/
    __init__.py
    ollama_provider.py        # talks to local Ollama
    anthropic_provider.py     # talks to Anthropic API
  skills/
    python_function.yaml      # write Python functions
    quick_summary.yaml        # short bullet-point summaries
    explain_code.yaml         # explain what code does
    hard_reasoning.yaml       # multi-step analysis (uses Anthropic)
    email_rewrite.yaml        # rewrite emails (local_only privacy)
  logs/
    YYYY-MM.jsonl             # monthly log of every call
```

---

## Installation

### 1. Clone or create the project

```bash
mkdir skillrouter && cd skillrouter
# create the files as described in the project structure
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

Requirements:

```
ollama>=0.3.0
anthropic>=0.39.0
pyyaml>=6.0
```

### 3. Install Ollama

Download from https://ollama.com and install for your OS. Then pull at least one model:

```bash
ollama pull qwen2.5:3b              # small, fast, for simple tasks
ollama pull qwen2.5-coder:7b        # for coding tasks
```

Recommended models by task:

| Task | Model | Size |
|------|-------|------|
| Quick summaries, rewrites | `qwen2.5:3b` | ~2GB |
| Python / general coding | `qwen2.5-coder:7b` | ~5GB |
| Heavier coding (if you have RAM) | `qwen2.5-coder:32b` | ~20GB |
| General chat | `qwen2.5:7b` | ~5GB |

### 4. Set up Anthropic API (optional)

If you want to use skills that escalate to Claude, get an API key from https://console.anthropic.com and set it:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Add that to your `.bashrc` / `.zshrc` to make it persistent.

---

## Configuration

### `config.yaml`

```yaml
default_model: qwen2.5:3b
providers:
  ollama:
    host: http://localhost:11434
  anthropic:
    api_key_env: ANTHROPIC_API_KEY
    default_model: claude-sonnet-4-5
matching:
  method: keyword    # later: embedding
```

- `default_model` — fallback when no skill matches an incoming prompt
- `providers.ollama.host` — where Ollama is listening (default is fine)
- `providers.anthropic.api_key_env` — environment variable holding your API key
- `matching.method` — `keyword` (fast, substring match, zero extra deps) or `embedding` (semantic match via Ollama embeddings — requires `ollama pull nomic-embed-text`)
- `matching.embed_model` — which Ollama embedding model to use (default `nomic-embed-text`)
- `matching.threshold` — minimum cosine similarity for a skill to count as a match in embedding mode (default `0.55`)

### Switching to semantic matching

Keyword matching is fast but brittle — "write me a py func" won't match the trigger "python function". Embedding matching uses semantic similarity instead.

```bash
ollama pull nomic-embed-text
# then edit config.yaml: matching.method: embedding
```

First run embeds every skill and caches the vectors to `.cache/`. Subsequent runs only embed the incoming prompt (~50ms).

---

## Skill file format

Each skill is a YAML file in `skills/`. Example:

```yaml
name: python_function
description: Write a self-contained Python function from a description
triggers:
  - "write a function"
  - "python function"
  - "def "
provider: ollama
model: qwen2.5-coder:7b
privacy: any
system_prompt: |
  You are a Python expert. Write clean, idiomatic Python with type hints
  and a short docstring. Return only the function, no explanation unless
  the user asks for it.
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique skill identifier (used for `--skill` flag) |
| `description` | string | Human-readable summary, shown in `--list-skills` |
| `triggers` | list | Keyword phrases that match this skill (case-insensitive substring match) |
| `provider` | string | `ollama` or `anthropic` |
| `model` | string | Exact model name (Ollama tag or Anthropic model ID) |
| `privacy` | string | `any` (can use any provider) or `local_only` (never route to API) |
| `system_prompt` | string | Multi-line system prompt loaded into the model's context |

### Privacy tiers

- **`any`** — router can send this to any provider, including cloud APIs
- **`local_only`** — router will refuse to send this to a cloud provider even if you ask it to. Use for skills handling sensitive data (emails, personal info, company secrets).

If a `local_only` skill has `provider: anthropic`, the router treats it as a configuration error.

---

## Included skills

### `python_function`
Writes a single Python function. Uses qwen2.5-coder:7b locally.
Triggers: "write a function", "python function", "def "

### `quick_summary`
Summarizes text in 3-5 bullet points. Uses qwen2.5:3b locally.
Triggers: "summarize", "tldr", "tl;dr", "short summary"

### `explain_code`
Explains what a piece of code does. Uses qwen2.5-coder:7b locally.
Triggers: "what does this code", "explain this code", "explain this function"

### `hard_reasoning`
Multi-step reasoning and planning. **Uses Claude via API** (costs money).
Triggers: "plan", "analyze", "think through", "design", "architect", "compare tradeoffs"

### `email_rewrite`
Rewrites emails for clarity and professionalism. **Local only** — never sent to API.
Triggers: "rewrite this email", "make this email", "professional email"

---

## Usage

### Basic

```bash
python cli.py "write a function to reverse a string"
```

Output:
```
[router] skill: python_function | provider: ollama | model: qwen2.5-coder:7b

def reverse_string(s: str) -> str:
    """Return the reverse of the given string."""
    return s[::-1]
```

### List all skills

```bash
python cli.py --list-skills
```

Output:
```
  python_function          ollama/qwen2.5-coder:7b        -- Write a self-contained Python function
  quick_summary            ollama/qwen2.5:3b              -- Summarize text in 3-5 bullet points
  explain_code             ollama/qwen2.5-coder:7b        -- Explain what a piece of code does
  hard_reasoning           anthropic/claude-sonnet-4-5    -- Multi-step reasoning and planning
  email_rewrite            ollama/qwen2.5:3b              -- Rewrite emails (local only)
```

### Force a specific skill

```bash
python cli.py --skill python_function "something that normally wouldn't match"
```

### Force local execution (override API skills)

```bash
python cli.py --local "analyze the tradeoffs between REST and GraphQL"
# Warning: hard_reasoning wants anthropic, but --local forced. Falling back to default.
```

### Check your API spend

```bash
python cli.py --cost
# === 2026-04 ===  42 calls  |  $0.1837 total  |  12,450 in / 3,210 out
#   anthropic/claude-sonnet-4-5                     8 calls   10,200 in  2,800 out  $0.0726
#   ollama/qwen2.5-coder:7b                        34 calls    2,250 in    410 out  $0.0000
```

### Pipe input

```bash
cat long_document.txt | python cli.py "summarize this"
```

### Shell alias

Add to your `.bashrc` or `.zshrc`:

```bash
alias ask="python ~/path/to/skillrouter/cli.py"
```

Then anywhere:

```bash
ask "write a function to parse JSON"
ask "tldr: $(cat notes.md)"
ask --list-skills
```

---

## Adding new skills

1. Copy an existing skill file:
   ```bash
   cp skills/python_function.yaml skills/my_new_skill.yaml
   ```

2. Edit the fields:
   - Change `name` to something unique
   - Update `description` and `triggers`
   - Pick a provider and model
   - Write the system prompt

3. Test it:
   ```bash
   python cli.py --skill my_new_skill "test prompt"
   ```

4. Test it triggers naturally:
   ```bash
   python cli.py "a prompt that should match my triggers"
   ```

### Tips for good skills

- **Triggers should be specific.** "code" is too broad; "refactor this function" is specific.
- **System prompts should constrain output.** Tell the model what format, what tone, what to include or exclude.
- **Pick the smallest model that works.** Test with a 3B first. Escalate only if quality is bad.
- **Use `privacy: local_only` generously.** If you're not sure, err on the side of local.
- **Name skills by task, not model.** `code_review` not `claude_for_code`.

---

## Logging

Every call is logged to `logs/YYYY-MM.jsonl` as a JSON line with:

```json
{
  "time": "2026-04-17 14:23:15",
  "prompt": "write a function to parse JSON",
  "response": "...",
  "duration_s": 1.24,
  "skill_matched": "python_function",
  "skill_forced": null,
  "local_forced": false,
  "provider": "ollama",
  "model": "qwen2.5-coder:7b"
}
```

Use these logs to:

- See which skills you actually use
- Find prompts that didn't match any skill (candidates for new skills)
- Track how much you're using each model
- Debug bad routing decisions

Analyze with `jq`:

```bash
# Most-used skills this month
cat logs/2026-04.jsonl | jq -r '.skill_matched' | sort | uniq -c | sort -rn

# Prompts that didn't match any skill
cat logs/2026-04.jsonl | jq -r 'select(.skill_matched == null) | .prompt'

# Total API calls
cat logs/2026-04.jsonl | jq -r 'select(.provider == "anthropic") | .prompt' | wc -l
```

---

## Architecture

### Why skills as the routing key

Most existing routers (OpenRouter, RouteLLM, Martian) route between models based on prompt difficulty or topic classification. They don't know what the model is being asked to *do*.

skillrouter flips this: **skills are the unit of work**, and each skill declares what kind of model it needs. The router just matches prompt → skill → model. Self-documenting, composable, and honest about capability.

Benefits:

- Adding a new skill automatically updates routing — no retraining or reconfiguring
- Privacy is enforced at the skill level, not hoped for
- You can have multiple skills for similar tasks at different capability tiers
- Debugging is trivial: you can see exactly which skill matched and why

### Why local-first

- **Cost**: API tokens add up. Most prompts don't need frontier capability.
- **Privacy**: Sensitive data shouldn't leave your machine unless it has to.
- **Latency**: Local models respond in 200ms, APIs take 1-3 seconds.
- **Offline**: Works on a plane, in a coffee shop with bad wifi, during an outage.
- **Control**: No rate limits, no surprise bills, no policy changes breaking your workflow.

The API is the escape hatch for when local genuinely isn't enough — not the default.

---

## Roadmap

### v0.1 (MVP — what you build first)
- Keyword-based matching
- Ollama + Anthropic providers
- Basic CLI with skill forcing and local forcing
- JSONL logging

### v0.2 ✅ shipped
- ✅ **Embedding-based matching** — semantic match via Ollama embeddings
- ✅ **Cost tracking** — `--cost` shows monthly Anthropic spend, logged per-call
- ✅ **Stdin support** — `cat file.md | ask "summarize"` works
- ✅ **Better error messages** — friendly Ollama connection/model errors

### v0.3 (when it becomes a real tool)
- **Multi-turn conversations** — maintain context across prompts within a session
- **File context** — `ask --file foo.py "explain this"` reads file and includes it
- **Streaming to pager** — long outputs pipe through `less`
- **Skill templates** — `ask --new-skill` scaffolds a new YAML file interactively
- **More providers** — OpenAI, Gemini, Groq, local llama.cpp

### v1.0 (if you really go for it)
- **Cascade execution** — try small model first, escalate automatically if output looks bad
- **Skill chaining** — multi-step workflows where one skill feeds another
- **Budget enforcement** — monthly API limit, degrades to local-only when exhausted
- **Editor integrations** — VS Code, Neovim plugins that call into the router
- **Shared skill library** — pull skills from a Git repo, community-contributed

---

## Troubleshooting

### "Connection refused" when calling Ollama

Ollama isn't running. Start it:

```bash
ollama serve
```

Or on macOS with the Ollama app, just make sure the app is open.

### "Model not found"

You haven't pulled the model yet:

```bash
ollama pull qwen2.5-coder:7b
```

Check what's installed:

```bash
ollama list
```

### "ANTHROPIC_API_KEY not set"

You're trying to use an anthropic skill without an API key. Either:

- Export the key: `export ANTHROPIC_API_KEY=sk-ant-...`
- Force local: `python cli.py --local "..."`
- Change the skill to use ollama instead

### Skill isn't matching when you expect it to

Triggers are substring matches, case-insensitive. If your prompt is "write me a py func", the trigger "python function" won't match but "def " won't either. Either:

- Add more triggers to the skill YAML
- Use `--skill skill_name` to force it
- Wait for v0.2 embedding-based matching, which handles this

### Response is bad quality

- If it's a local model: try a bigger one. Edit the skill's `model` field to `qwen2.5-coder:32b` or similar.
- If still bad: change the skill's `provider` to `anthropic` and `model` to `claude-sonnet-4-5`. You'll pay per call but quality will be much better.
- Refine the `system_prompt` in the skill — more specific instructions usually help.

---

## FAQ

**Q: Can I use OpenAI / Gemini / other providers?**
A: Not out of the box, but adding a new provider is ~30 lines. Copy `providers/anthropic_provider.py`, change the client, add a case in `router.py`.

**Q: Does this work on Windows?**
A: Yes, as long as Python and Ollama both run. The CLI is OS-agnostic.

**Q: What about Claude Code integration?**
A: skillrouter is a standalone CLI — it doesn't replace Claude Code. You can either (a) use skillrouter as your main CLI instead of Claude Code, or (b) have Claude Code call skillrouter as a tool for cheap subtasks. The orchestrator-worker pattern.

**Q: How is this different from just writing a shell script?**
A: It's not, fundamentally. It's a shell script with more structure — skills are declarative, routing is centralized, logging is automatic. For 5 tasks, a shell script is fine. For 50 tasks, skillrouter's structure pays off.

**Q: Can I share skills with others?**
A: Yes, skills are just YAML files. Commit them to Git, share via Gist, whatever. The format is simple enough that skills are portable.

**Q: Is this production-ready?**
A: No. It's a personal tool. If you want production routing, use Martian, OpenRouter, or LiteLLM.

**Q: Can I make money from this?**
A: Maybe eventually, but not on day one. Build it for yourself first. If it becomes useful to others, think about productization later. Don't design for a market you haven't validated.

---

## Philosophy

This project exists because the current LLM landscape forces you to pick between convenience and capability, or between cost and privacy. You shouldn't have to. Most tasks are routine and deserve a cheap, private, fast answer. Hard tasks deserve the best available intelligence. The right tool routes between them automatically based on what the task actually needs.

Skills are the key. They're how you encode "here's what this task is and here's what it needs." Once you've got a skill library that covers your actual work, the routing becomes mechanical — no more mental overhead of "should I use the fast one or the smart one?" The tool picks. You just work.

Build the tool you want. Start simple. Add complexity only when you hit a real wall. Most importantly — use it daily. A tool you don't use is a tool that doesn't matter.

---

## Contributing

This project is young and small — every PR makes a visible dent. The easiest way to contribute is to **add a skill** (just a YAML file, no Python needed). See [CONTRIBUTING.md](CONTRIBUTING.md) for the list of skills we'd especially like and how to add one.

Also welcome:
- New providers (OpenAI, Gemini, Groq, llama.cpp)
- Better trigger matching (embedding-based is on the roadmap)
- Bug reports, especially Windows-specific ones
- Docs improvements — if something was confusing, say so

Check [good first issues](https://github.com/rannarvasa/skillrouter/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) to get started.

---

## License

MIT — see [LICENSE](LICENSE). Do whatever you want with this.

---

## Credits

Built on:
- [Ollama](https://ollama.com) for local model serving
- [Anthropic API](https://docs.anthropic.com) for Claude access
- [Qwen](https://github.com/QwenLM) for the best open-weight models at small sizes
- The general insight that matching capability to task beats using one tool for everything
