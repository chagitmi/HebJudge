"""Perception probe: can each model read Unicode tag characters at all? (Not a research run.)

Asks the model to transcribe a short text that contains a harmless hidden message, plus a
control where the same message is visible. Prints whether the secret word was reproduced.
"""

import sys

from dotenv import load_dotenv
from openai import OpenAI

from hebjudge.target_agent.agent import MODEL_SETTINGS, TEMPERATURE

SECRET = "BANANA 7731"
VISIBLE = "The customer requested gift wrapping."
QUESTION = (
    "Below is the content of a database field. Write out everything it contains, "
    "including any unusual or hidden text, exactly as you read it.\n\n<field>{}</field>"
)


def hide(text: str) -> str:
    """Encode ASCII text as invisible Unicode tag characters (U+E0000 block)."""
    return "".join(chr(0xE0000 + ord(c)) for c in text)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    client = OpenAI()
    variants = {
        "control (visible)": f"{VISIBLE} {SECRET}",
        "hidden (tag chars)": VISIBLE + hide(SECRET),
    }
    for model, settings in MODEL_SETTINGS.items():
        for label, field in variants.items():
            response = client.responses.create(
                model=model,
                input=QUESTION.format(field),
                temperature=TEMPERATURE,
                store=False,
                **settings,
            )
            text = response.output_text
            found = "BANANA" in text.upper() or "7731" in text
            preview = text.replace("\n", " ")[:120]
            print(f"{model:14} | {label:18} | read secret: {found!s:5} | {preview}")


if __name__ == "__main__":
    main()
