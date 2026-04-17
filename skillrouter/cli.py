import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from router import Router


ROOT = Path(__file__).resolve().parent


def list_skills(router: Router) -> None:
    for s in router.skills:
        if s.model:
            detail = f"{s.provider or 'ollama'}/{s.model}"
            print(f"  {s.name:<20} {detail:<40} -- {s.description}")
            continue
        try:
            pick = router.resolve_for_skill(s, local_forced=False)
            resolved = f"{pick['provider']}/{pick['model']}"
        except Exception as e:
            resolved = f"UNRESOLVED ({e})"
        cap = f"{s.kind}/{s.strength}"
        print(f"  {s.name:<20} {cap:<22} -> {resolved:<35} -- {s.description}")


def doctor(router: Router) -> None:
    reg = router.registry
    print("=== Ollama ===")
    if reg.ollama_error:
        print(f"  error: {reg.ollama_error}")
    elif not reg.installed_ollama:
        print("  no models installed")
    else:
        for m in reg.installed_ollama:
            kinds = ",".join(m["kinds"])
            print(f"  {m['tag']:<30} strength={m['strength']:<9} kinds=[{kinds}]")

    print("\n=== Anthropic ===")
    if reg.api_available:
        for tag, meta in reg.anthropic_models.items():
            print(f"  {tag:<30} strength={meta.get('strength', 'frontier')}  (API key set)")
    else:
        print("  ANTHROPIC_API_KEY not set — API models unreachable")

    print("\n=== Skills ===")
    for s in router.skills:
        if s.model:
            print(f"  {s.name:<20} explicit -> {s.provider or 'ollama'}/{s.model}")
            continue
        try:
            pick = router.resolve_for_skill(s, local_forced=False)
            print(
                f"  {s.name:<20} {s.kind}/{s.strength}"
                f"  -> {pick['provider']}/{pick['model']}  ({pick['reason']})"
            )
        except Exception as e:
            print(f"  {s.name:<20} {s.kind}/{s.strength}  -> UNRESOLVED: {e}")


def log_call(root: Path, entry: dict) -> None:
    logs_dir = root / "logs"
    logs_dir.mkdir(exist_ok=True)
    month = datetime.now().strftime("%Y-%m")
    path = logs_dir / f"{month}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_stdin_if_piped() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="skillrouter",
        description="Route prompts to the right LLM based on a library of skills.",
    )
    parser.add_argument("prompt", nargs="*", help="The prompt to send")
    parser.add_argument("--list-skills", action="store_true", help="List skills with resolved models")
    parser.add_argument("--doctor", action="store_true", help="Show installed models + skill routing")
    parser.add_argument("--skill", help="Force a specific skill by name")
    parser.add_argument("--local", action="store_true", help="Force local execution (no API)")
    parser.add_argument("--cost", action="store_true", help="Show this month's API spend and exit")
    args = parser.parse_args()

    router = Router(ROOT)

    if args.doctor:
        doctor(router)
        return 0

    if args.list_skills:
        list_skills(router)
        return 0

    if args.cost:
        show_cost(ROOT)
        return 0

    prompt = " ".join(args.prompt).strip()
    piped = read_stdin_if_piped().strip()
    if piped:
        prompt = f"{prompt}\n\n{piped}" if prompt else piped

    if not prompt:
        parser.print_help()
        return 1

    try:
        decision = router.resolve(
            prompt, forced_skill=args.skill, local_forced=args.local
        )
    except (ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(
        f"[router] skill: {decision['skill']} | "
        f"provider: {decision['provider']} | model: {decision['model']} "
        f"| reason: {decision['reason']}\n"
    )

    try:
        provider = router.make_provider(decision["provider"])
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    start = time.time()
    try:
        result = provider.generate(
            decision["model"], decision["system_prompt"], prompt
        )
    except Exception as e:
        print(f"\nerror calling {decision['provider']}: {e}", file=sys.stderr)
        return 4
    duration = time.time() - start

    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)
    cost_usd = 0.0
    pricing = router.pricing(decision["provider"], decision["model"])
    if pricing:
        cost_usd = (
            input_tokens * pricing["input"] + output_tokens * pricing["output"]
        ) / 1_000_000

    if pricing or input_tokens:
        tail = f"[router] tokens: {input_tokens} in / {output_tokens} out"
        if cost_usd:
            tail += f" | cost: ${cost_usd:.4f}"
        print(tail)

    log_call(
        ROOT,
        {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "prompt": prompt,
            "response": result.get("text", ""),
            "duration_s": round(duration, 3),
            "skill_matched": decision["skill"],
            "skill_forced": args.skill,
            "local_forced": args.local,
            "provider": decision["provider"],
            "model": decision["model"],
            "model_reason": decision["reason"],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 6),
        },
    )
    return 0


def show_cost(root: Path) -> None:
    logs_dir = root / "logs"
    month = datetime.now().strftime("%Y-%m")
    path = logs_dir / f"{month}.jsonl"
    if not path.exists():
        print(f"no log file for {month} yet")
        return

    by_model: dict[str, dict] = {}
    total_cost = 0.0
    total_in = 0
    total_out = 0
    calls = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            calls += 1
            cost = e.get("cost_usd", 0) or 0
            inp = e.get("input_tokens", 0) or 0
            out = e.get("output_tokens", 0) or 0
            total_cost += cost
            total_in += inp
            total_out += out
            key = f"{e.get('provider', '?')}/{e.get('model', '?')}"
            row = by_model.setdefault(key, {"calls": 0, "in": 0, "out": 0, "cost": 0.0})
            row["calls"] += 1
            row["in"] += inp
            row["out"] += out
            row["cost"] += cost

    print(f"=== {month} ===  {calls} calls  |  ${total_cost:.4f} total  |  {total_in:,} in / {total_out:,} out")
    for key, row in sorted(by_model.items(), key=lambda kv: -kv[1]["cost"]):
        print(
            f"  {key:<45}  {row['calls']:>4} calls  "
            f"{row['in']:>8,} in  {row['out']:>7,} out  ${row['cost']:.4f}"
        )


if __name__ == "__main__":
    sys.exit(main())
