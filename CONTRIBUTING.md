# Contributing to skillrouter

Thanks for considering a contribution. skillrouter is a small, focused tool and the bar for new features is "does it make routing smarter or skills easier to write?" Everything else is probably scope creep.

## The easiest contribution: add a skill

Skills are YAML files. No Python required. If there's a task you do often that skillrouter doesn't cover, add it.

1. Copy an existing skill in [`skillrouter/skills/`](skillrouter/skills/) as a template.
2. Edit `name`, `description`, `triggers`, `provider`, `model`, `privacy`, and `system_prompt`.
3. Test it:
   ```bash
   python skillrouter/cli.py --skill your_skill_name "test prompt"
   python skillrouter/cli.py "a prompt your triggers should match"
   ```
4. Open a PR with just the new YAML file.

See the [Skill file format](README.md#skill-file-format) section of the README for field details.

### Skills we'd especially like

- `commit_message` — write a conventional commit from a diff (local)
- `regex_explain` — explain a regex in plain English (local)
- `sql_query` — write a SQL query from natural language (local, coder model)
- `bash_oneliner` — write a shell one-liner (local)
- `translate` — translate between languages (local)
- `json_fix` — repair malformed JSON (local)
- `changelog_entry` — turn a diff into a changelog line (local)
- `test_scaffold` — generate unit tests from a function signature (local, coder model)

If you add one, drop it in `skills/` and open a PR. Short description in the PR body is fine — no RFC needed.

## Adding a provider

Currently supported: Ollama (local), Anthropic (API). Adding OpenAI, Gemini, Groq, or llama.cpp is a good contribution.

1. Create `skillrouter/providers/<name>_provider.py` following the shape of `anthropic_provider.py`. It needs one method: `generate(model, system_prompt, user_prompt) -> str`.
2. Wire it into `Router.make_provider` in `router.py`.
3. Add any needed config keys to `config.yaml`.
4. Update the README's provider list and add a skill that uses it.

## Code changes

- Keep PRs small and focused. One feature or fix per PR.
- Match existing style. No framework, no heavy abstractions — this is a ~400-line tool.
- If it adds a user-facing flag or changes behavior, update the README.
- Don't add dependencies casually. Each new dep should earn its place.

## Good first issues

Look for the `good first issue` label on [open issues](https://github.com/rannarvasa/skillrouter/issues). If you don't see one that fits, pick something from the "Skills we'd especially like" list above — that's the lowest-friction way to contribute.

## Reporting bugs

Open an issue with:
- What you ran (`python cli.py ...`)
- What you expected
- What happened instead
- Output of `python cli.py --doctor`

## Philosophy

skillrouter is a personal tool that happens to be useful to others. It will stay simple. PRs that add "enterprise" features, heavy config systems, web UIs, or telemetry will be politely declined. PRs that make skills easier to write, routing smarter, or providers more pluggable are very welcome.
