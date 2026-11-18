"""Serve the v1 mock store agent over local HTTP, so it can be tested like a real agent.

Used to check the HTTP adapter end to end against an agent whose behavior is known (v2 design,
section 3). Listens on 127.0.0.1 only. Every message calls the OpenAI API and costs a fraction of
a cent.

Usage:
    python scripts/serve_store_agent.py --model gpt-4o-mini --language he

Request:  POST /chat  {"message": "...", "session_id": "..."}
Response: {"reply": "...", "tool_calls": [{"name": ..., "arguments": {...}}]}
"""

import argparse
import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv
from openai import OpenAI

from hebjudge.target_agent.agent import MODEL_SETTINGS, run_agent
from hebjudge.target_agent.tools import MockStore


def make_handler(client: OpenAI, model: str, language: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (name required by http.server)
            if self.path != "/chat":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                message = payload["message"]
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
                self.send_error(400, "expected JSON with a 'message' field")
                return

            result = run_agent(client, model, language, message, store=MockStore())
            body = json.dumps(
                {
                    "reply": result.final_text,
                    "tool_calls": [asdict(c) for c in result.tool_calls],
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            print(f"{self.address_string()} {format % args}")

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="gpt-4o-mini", choices=sorted(MODEL_SETTINGS))
    parser.add_argument("--language", default="he", choices=["he", "en"])
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    load_dotenv()
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port), make_handler(OpenAI(), args.model, args.language)
    )
    print(f"Store agent ({args.model}, {args.language}) on http://127.0.0.1:{args.port}/chat")
    print("Every message costs a fraction of a cent. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
