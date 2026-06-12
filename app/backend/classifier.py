"""Vision classification: one model call per image, validated against the schema.

Two retry concerns, deliberately kept separate:
- transport errors (network, 5xx, rate limits): the OpenAI SDK's built-in
  exponential backoff handles these (max_retries on the client)
- validation errors (output that fails the schema): re-prompt with the
  error text, up to MAX_VALIDATION_RETRIES, then raise ClassificationError
"""

import base64
import json
import logging
import mimetypes
import os
import re
from pathlib import Path

from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from app.backend.prompts import CLASSIFICATION_SYSTEM_PROMPT, build_user_content
from app.backend.schemas import GarmentAttributes

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"
MAX_VALIDATION_RETRIES = 2

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class ClassificationError(Exception):
    """Model could not produce schema-valid output within the retry budget."""


def parse_model_output(text: str) -> GarmentAttributes:
    """Parse raw model text into GarmentAttributes.

    Structured outputs should make this trivial, but markdown fences and
    surrounding prose are handled defensively: the guard costs nothing and
    the failure mode (a lost upload) is expensive.
    """
    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return GarmentAttributes.model_validate(json.loads(text))


def get_client() -> OpenAI:
    return OpenAI(max_retries=3)


def _encode_image(image_path: Path) -> tuple[str, str]:
    data = Path(image_path).read_bytes()
    media_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
    return base64.b64encode(data).decode("ascii"), media_type


def classify_image(
    image_path: Path,
    client: OpenAI | None = None,
    model: str | None = None,
) -> GarmentAttributes:
    client = client or get_client()
    model = model or os.environ.get("MODEL", DEFAULT_MODEL)
    image_b64, media_type = _encode_image(image_path)
    messages = [
        {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": build_user_content(image_b64, media_type)},
    ]

    last_error: Exception | None = None
    for attempt in range(1 + MAX_VALIDATION_RETRIES):
        raw = None
        try:
            completion = client.chat.completions.parse(
                model=model,
                messages=messages,
                response_format=GarmentAttributes,
            )
            message = completion.choices[0].message
            if getattr(message, "parsed", None) is not None:
                return message.parsed
            raw = message.content or ""
            return parse_model_output(raw)
        except OpenAIError as exc:
            # auth/connection/API errors are not fixable by re-prompting, and
            # the SDK's backoff already retried the transient ones; convert so
            # the caller's failure path (status=failed) always runs
            raise ClassificationError(f"model API call failed: {exc}") from exc
        except (ValidationError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning(
                "classification attempt %d/%d failed validation: %s; raw output: %r",
                attempt + 1,
                1 + MAX_VALIDATION_RETRIES,
                exc,
                raw,
            )
            messages = messages + [
                {
                    "role": "user",
                    "content": (
                        "Your previous response failed schema validation:\n"
                        f"{exc}\n\n"
                        "Return only a corrected JSON object that matches the "
                        "schema exactly."
                    ),
                }
            ]

    raise ClassificationError(
        f"no schema-valid output after {1 + MAX_VALIDATION_RETRIES} attempts"
    ) from last_error
