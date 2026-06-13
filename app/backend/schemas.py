"""Output contract for the vision classifier.

Closed vocabularies (enums) where the eval needs exact matching; free text
where descriptive richness matters more than measurability. Every enum has
an OTHER escape hatch so the model is never forced into a wrong label.
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class GarmentType(str, Enum):
    DRESS = "dress"
    TOP = "top"
    SHIRT = "shirt"
    BLOUSE = "blouse"
    SWEATER = "sweater"
    JACKET = "jacket"
    COAT = "coat"
    TROUSERS = "trousers"
    JEANS = "jeans"
    SKIRT = "skirt"
    SHORTS = "shorts"
    JUMPSUIT = "jumpsuit"
    SUIT = "suit"
    ACTIVEWEAR = "activewear"
    SWIMWEAR = "swimwear"
    TRADITIONAL = "traditional_wear"
    OTHER = "other"


class Season(str, Enum):
    SPRING = "spring"
    SUMMER = "summer"
    FALL = "fall"
    WINTER = "winter"
    ALL_SEASON = "all_season"
    OTHER = "other"


class Occasion(str, Enum):
    CASUAL = "casual"
    FORMAL = "formal"
    BUSINESS = "business"
    ATHLETIC = "athletic"
    EVENING = "evening"
    FESTIVAL = "festival"
    CEREMONIAL = "ceremonial"
    OTHER = "other"


class LocationContext(BaseModel):
    """Geographic context visible in the image, if any.

    All fields are Optional by design: null is the correct answer for a
    studio shot. A confabulated country is worse than an honest unknown.
    """

    continent: Optional[str] = Field(
        None, description="Continent, only if clearly evidenced in the image."
    )
    country: Optional[str] = Field(
        None, description="Country, only if clearly evidenced in the image."
    )
    city: Optional[str] = Field(
        None, description="City, only if clearly evidenced in the image."
    )


class GarmentAttributes(BaseModel):
    description: str = Field(
        ...,
        description=(
            "2-4 sentence searchable description of the dominant garment using "
            "concrete fashion vocabulary (silhouette, neckline, hem, fabric finish)."
        ),
    )
    garment_type: GarmentType = Field(
        ..., description="Category of the dominant garment in the photo."
    )
    style: str = Field(
        ..., description="Style label in plain words, e.g. 'bohemian', 'streetwear'."
    )
    material: str = Field(
        ..., description="Apparent primary material, e.g. 'denim', 'linen blend'."
    )
    color_palette: list[str] = Field(
        ..., description="Dominant colors of the garment, e.g. ['indigo', 'cream']."
    )
    pattern: str = Field(
        ..., description="Surface pattern, e.g. 'floral print', 'solid'."
    )
    season: Season = Field(
        ..., description="Season the garment is most suited to."
    )
    occasion: Occasion = Field(
        ..., description="Occasion the garment is most suited to."
    )
    consumer_profile: str = Field(
        ..., description="Likely target consumer, e.g. 'young urban professionals'."
    )
    trend_notes: str = Field(
        ..., description="Trend relevance worth a designer's attention."
    )
    location_context: LocationContext = Field(
        ...,
        description=(
            "Location evidenced in the image. Use nulls unless the evidence is clear."
        ),
    )


class AnnotationIn(BaseModel):
    """Designer-supplied annotation. Distinct from AI output by living in its
    own table; `kind` separates quick tags from longer notes."""

    kind: Literal["tag", "note"]
    content: str = Field(..., min_length=1)
