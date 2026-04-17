import ollama


class OllamaProvider:
    name = "ollama"

    def __init__(self, host: str = "http://localhost:11434"):
        self.client = ollama.Client(host=host)

    def generate(self, model: str, system_prompt: str, user_prompt: str) -> str:
        chunks = []
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
        print()
        return "".join(chunks)
