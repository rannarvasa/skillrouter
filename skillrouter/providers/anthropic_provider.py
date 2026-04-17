import os
import anthropic


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key_env: str = "ANTHROPIC_API_KEY"):
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{api_key_env} not set. Export it (e.g. `export {api_key_env}=sk-ant-...`) "
                f"or use --local to force local execution."
            )
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate(self, model: str, system_prompt: str, user_prompt: str) -> dict:
        chunks = []
        with self.client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                chunks.append(text)
            final = stream.get_final_message()
        print()
        usage = getattr(final, "usage", None)
        return {
            "text": "".join(chunks),
            "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
            "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
        }
