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
    args = parser.parse_args()

    router = Router(ROOT)

    if args.doctor:
        doctor(router)
        return 0

    if args.list_skills:
        list_skills(router)
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
        response = provider.generate(
            decision["model"], decision["system_prompt"], prompt
        )
    except Exception as e:
        print(f"\nerror calling {decision['provider']}: {e}", file=sys.stderr)
        return 4
    duration = time.time() - start

    log_call(
        ROOT,
        {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "prompt": prompt,
            "response": response,
            "duration_s": round(duration, 3),
            "skill_matched": decision["skill"],
            "skill_forced": args.skill,
            "local_forced": args.local,
            "provider": decision["provider"],
            "model": decision["model"],
            "model_reason": decision["reason"],
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
