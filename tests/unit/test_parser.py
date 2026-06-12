"""Unit tests for model-output parsing and the validation retry loop.

The model client is always mocked: these tests pin down our behavior
(parsing, retry, failure persistence), not the model's.
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.backend import db
from app.backend.classifier import (
    ClassificationError,
    classify_image,
    parse_model_output,
)
from app.backend.main import process_classification
from app.backend.schemas import GarmentType

VALID_PAYLOAD = {
    "description": (
        "A cropped boxy denim jacket with a raw hem and silver-tone buttons, "
        "worn open over a white tee."
    ),
    "garment_type": "jacket",
    "style": "streetwear",
    "material": "denim",
    "color_palette": ["indigo", "white"],
    "pattern": "solid",
    "season": "fall",
    "occasion": "casual",
    "consumer_profile": "young urban adults",
    "trend_notes": "cropped denim silhouettes trending in streetwear",
    "location_context": {"continent": None, "country": None, "city": None},
}


def make_completion(content=None, parsed=None):
    message = SimpleNamespace(content=content, parsed=parsed)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_client(completions):
    parse = Mock(side_effect=completions)
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))
    )


@pytest.fixture
def image_file(tmp_path):
    path = tmp_path / "garment.jpg"
    path.write_bytes(b"\xff\xd8\xff fake jpeg bytes")
    return path


class TestParseModelOutput:
    def test_valid_payload_parses(self):
        attrs = parse_model_output(json.dumps(VALID_PAYLOAD))
        assert attrs.garment_type == GarmentType.JACKET
        assert attrs.color_palette == ["indigo", "white"]
        assert attrs.location_context.country is None

    def test_markdown_fenced_json_handled(self):
        text = "```json\n" + json.dumps(VALID_PAYLOAD) + "\n```"
        attrs = parse_model_output(text)
        assert attrs.garment_type == GarmentType.JACKET

    def test_surrounding_prose_handled(self):
        text = (
            "Here is the classification:\n"
            + json.dumps(VALID_PAYLOAD)
            + "\nHope that helps!"
        )
        attrs = parse_model_output(text)
        assert attrs.garment_type == GarmentType.JACKET

    def test_invalid_enum_rejected(self):
        bad = {**VALID_PAYLOAD, "garment_type": "spaceship"}
        with pytest.raises(ValidationError):
            parse_model_output(json.dumps(bad))

    def test_non_json_rejected(self):
        with pytest.raises(json.JSONDecodeError):
            parse_model_output("I cannot classify this image.")


class TestValidationRetry:
    def test_invalid_enum_then_fixed_on_retry(self, image_file):
        bad = {**VALID_PAYLOAD, "garment_type": "spaceship"}
        client = make_client(
            [
                make_completion(content=json.dumps(bad)),
                make_completion(content=json.dumps(VALID_PAYLOAD)),
            ]
        )

        attrs = classify_image(image_file, client=client)

        assert attrs.garment_type == GarmentType.JACKET
        assert client.chat.completions.parse.call_count == 2
        # the re-prompt must carry the validation error back to the model
        retry_messages = client.chat.completions.parse.call_args.kwargs["messages"]
        assert "spaceship" in retry_messages[-1]["content"]

    def test_exhausted_retries_raise(self, image_file):
        client = make_client([make_completion(content="not json at all")] * 3)

        with pytest.raises(ClassificationError):
            classify_image(image_file, client=client)

        assert client.chat.completions.parse.call_count == 3

    def test_sdk_parsed_object_used_directly(self, image_file):
        parsed = parse_model_output(json.dumps(VALID_PAYLOAD))
        client = make_client([make_completion(parsed=parsed)])

        attrs = classify_image(image_file, client=client)

        assert attrs is parsed


class TestFailurePersistence:
    def test_failed_classification_preserves_upload_row(self, image_file, tmp_path):
        conn = db.get_connection(tmp_path / "test.db")
        image_id = db.insert_image(conn, "garment.jpg", designer="lia")
        client = make_client([make_completion(content="garbage")] * 3)

        record = process_classification(conn, image_id, image_file, client=client)

        assert record["status"] == "failed"
        assert record["filename"] == "garment.jpg"
        assert record["designer"] == "lia"

    def test_successful_classification_persists_attributes(
        self, image_file, tmp_path
    ):
        conn = db.get_connection(tmp_path / "test.db")
        image_id = db.insert_image(conn, "garment.jpg")
        client = make_client([make_completion(content=json.dumps(VALID_PAYLOAD))])

        record = process_classification(conn, image_id, image_file, client=client)

        assert record["status"] == "classified"
        assert record["garment_type"] == "jacket"
        assert record["style"] == "streetwear"
        assert record["material"] == "denim"
        assert record["pattern"] == "solid"
        assert record["color_palette"] == "indigo,white"
        assert record["attributes"]["material"] == "denim"
        # description must land in the search index
        hit = conn.execute(
            "SELECT image_id FROM images_fts WHERE images_fts MATCH 'denim'"
        ).fetchone()
        assert hit["image_id"] == image_id
