import ollama


class OllamaProvider:
    name = "ollama"

    def __init__(self, host: str = "http://localhost:11434"):
        self.client = ollama.Client(host=host)

    def generate(self, model: str, system_prompt: str, user_prompt: str) -> dict:
        chunks = []
        prompt_tokens = 0
        completion_tokens = 0
        try:
            stream = self.client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                stream=True,
            )
            for part in stream:
                piece = part.get("message", {}).get("content", "")
                if piece:
                    print(piece, end="", flush=True)
                    chunks.append(piece)
                if part.get("done"):
                    prompt_tokens = part.get("prompt_eval_count", 0) or 0
                    completion_tokens = part.get("eval_count", 0) or 0
        except Exception as e:
            msg = str(e).lower()
            if "connection" in msg or "refused" in msg:
                raise RuntimeError(
                    "can't reach Ollama. Is it running? Try `ollama serve` "
                    "or open the Ollama app."
                )
            if "not found" in msg or "model" in msg and "pull" in msg:
                raise RuntimeError(
                    f"model '{model}' not installed. Run: `ollama pull {model}`"
                )
            raise
        print()
        return {
            "text": "".join(chunks),
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
        }
