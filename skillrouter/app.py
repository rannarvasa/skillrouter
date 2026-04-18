"""Minimal Tk GUI for skillrouter. Type a prompt, see which skill/model was picked,
see the response. No dependencies beyond the rest of skillrouter."""
import io
import queue
import threading
import tkinter as tk
from contextlib import redirect_stdout
from pathlib import Path
from tkinter import scrolledtext, ttk

from router import Router


ROOT = Path(__file__).resolve().parent


class SkillRouterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("skillrouter")
        self.root.geometry("900x700")
        self.router = Router(ROOT)
        self.queue: queue.Queue = queue.Queue()
        self.running = False
        self._build_ui()
        if self.router.no_models_installed:
            self._show_onboarding()
        else:
            self._show_detected_models()
        self.root.after(100, self._pump_queue)

    def _show_onboarding(self):
        self.send_btn.configure(state="disabled")
        self._set_output(Router.onboarding_message())
        self.route_label.configure(text="route: no models installed")
        self.status.configure(text="install Ollama + pull a model, then reopen")

    def _show_detected_models(self):
        tags = [m["tag"] for m in self.router.registry.installed_ollama]
        self.status.configure(
            text=f"ready  |  {len(tags)} Ollama models detected: {', '.join(tags[:4])}"
            + (" ..." if len(tags) > 4 else "")
        )

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Prompt", font=("", 11, "bold")).pack(anchor="w")
        self.prompt = scrolledtext.ScrolledText(top, height=5, wrap="word", font=("Segoe UI", 10))
        self.prompt.pack(fill="x")
        self.prompt.bind("<Control-Return>", lambda e: self._submit())

        controls = ttk.Frame(self.root)
        controls.pack(fill="x", padx=10)
        self.send_btn = ttk.Button(controls, text="Send  (Ctrl+Enter)", command=self._submit)
        self.send_btn.pack(side="left")
        self.local_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="--local (force local)", variable=self.local_var).pack(side="left", padx=12)
        self.force_skill = tk.StringVar(value="(auto)")
        skill_names = ["(auto)"] + [s.name for s in self.router.skills]
        ttk.Label(controls, text="skill:").pack(side="left")
        ttk.Combobox(controls, textvariable=self.force_skill, values=skill_names, width=20, state="readonly").pack(side="left", padx=4)

        self.route_label = ttk.Label(self.root, text="route: (no prompt yet)", foreground="#555")
        self.route_label.pack(fill="x", padx=12, pady=(10, 2), anchor="w")

        mid = ttk.Frame(self.root)
        mid.pack(fill="both", expand=True, padx=10, pady=4)
        ttk.Label(mid, text="Response", font=("", 11, "bold")).pack(anchor="w")
        self.output = scrolledtext.ScrolledText(mid, wrap="word", font=("Consolas", 10))
        self.output.pack(fill="both", expand=True)
        self.output.configure(state="disabled")

        self.status = ttk.Label(self.root, text="ready", foreground="#333")
        self.status.pack(fill="x", padx=12, pady=(0, 8), anchor="w")

    def _set_output(self, text: str, append: bool = False):
        self.output.configure(state="normal")
        if not append:
            self.output.delete("1.0", "end")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _submit(self):
        if self.running:
            return
        prompt = self.prompt.get("1.0", "end").strip()
        if not prompt:
            return

        self.running = True
        self.send_btn.configure(state="disabled", text="Working...")
        self._set_output("")
        self.status.configure(text="resolving skill...")

        forced = self.force_skill.get()
        forced = None if forced == "(auto)" else forced
        local = self.local_var.get()

        t = threading.Thread(
            target=self._worker, args=(prompt, forced, local), daemon=True
        )
        t.start()

    def _worker(self, prompt: str, forced_skill, local_forced: bool):
        try:
            decision = self.router.resolve(prompt, forced_skill=forced_skill, local_forced=local_forced)
        except Exception as e:
            self.queue.put(("error", f"routing error: {e}"))
            return

        route_text = (
            f"skill: {decision['skill'] or '(default fallback)'}  |  "
            f"{decision['provider']}/{decision['model']}  |  {decision['reason']}"
        )
        self.queue.put(("route", route_text))

        final_prompt = prompt
        if decision.get("tool") == "web":
            self.queue.put(("status", "searching the web..."))
            try:
                from tools.web import search_and_fetch
                context = search_and_fetch(prompt)
                final_prompt = f"{context}\n\n---\n\nUSER QUESTION: {prompt}"
                self.queue.put(("status", f"fetched {len(context)} chars of web context. generating..."))
            except Exception as e:
                self.queue.put(("error", f"web tool error: {e}"))
                return
        else:
            self.queue.put(("status", "generating..."))

        try:
            provider = self.router.make_provider(decision["provider"])
        except Exception as e:
            self.queue.put(("error", f"provider error: {e}"))
            return

        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                result = provider.generate(decision["model"], decision["system_prompt"], final_prompt)
        except Exception as e:
            self.queue.put(("error", f"generation error: {e}"))
            return

        text = result.get("text", "") or buf.getvalue()
        ip = result.get("input_tokens", 0)
        op = result.get("output_tokens", 0)
        pricing = self.router.pricing(decision["provider"], decision["model"])
        cost = 0.0
        if pricing:
            cost = (ip * pricing["input"] + op * pricing["output"]) / 1_000_000

        self.queue.put(("response", text))
        footer = f"done  |  tokens: {ip} in / {op} out"
        if cost:
            footer += f"  |  ${cost:.4f}"
        self.queue.put(("status", footer))
        self.queue.put(("done", None))

    def _pump_queue(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "route":
                    self.route_label.configure(text=f"route: {payload}")
                elif kind == "status":
                    self.status.configure(text=payload)
                elif kind == "response":
                    self._set_output(payload)
                elif kind == "error":
                    self._set_output(payload)
                    self.status.configure(text="error")
                    self.running = False
                    self.send_btn.configure(state="normal", text="Send  (Ctrl+Enter)")
                elif kind == "done":
                    self.running = False
                    self.send_btn.configure(state="normal", text="Send  (Ctrl+Enter)")
        except queue.Empty:
            pass
        self.root.after(100, self._pump_queue)


def main():
    root = tk.Tk()
    SkillRouterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
