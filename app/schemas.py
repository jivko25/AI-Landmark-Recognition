"""Response models. They also drive the OpenAPI docs at /docs."""

from typing import Literal

from pydantic import BaseModel, Field

VerifyMode = Literal["auto", "always", "never"]
VerificationStatus = Literal["skipped", "confirmed", "corrected", "no_landmark", "disputed", "unavailable", "error"]


class Candidate(BaseModel):
    name: str = Field(description="Име на забележителността според локалния модел")
    score: float = Field(description="Оценка от 0 до 1")


class Landmark(BaseModel):
    name: str | None = Field(description="Крайният отговор; null ако на снимката няма разпозната забележителност")
    score: float | None = Field(description="Оценката на локалния модел за това име (null ако Gemini е дал име извън кандидатите)")
    source: Literal["local", "gemini", "local+gemini"] = Field(description="Кой е дал крайния отговор")
    confident: bool = Field(
        description="false, ако локалният модел е несигурен и Gemini не е потвърдил (грешка, спор или изключен)"
    )


class Coordinates(BaseModel):
    lat: float
    lon: float


class LandmarkInfo(BaseModel):
    found: bool = Field(description="Дали е намерена информация")
    message: str | None = Field(None, description="Обяснение, когато found е false")
    title: str | None = None
    summary: str | None = Field(None, description="Кратко описание (първите изречения от Wikipedia)")
    language: str | None = Field(None, description="Езикът на title/summary/url")
    url: str | None = None
    image: str | None = None
    coordinates: Coordinates | None = None
    english_title: str | None = None
    english_url: str | None = None
    source: Literal["wikipedia"] | None = None


class GeminiVerdict(BaseModel):
    """Schema Gemini must answer with (structured output)."""

    landmark: str | None = Field(
        description="Common English name of the landmark in the photo, or null if no landmark can be identified."
    )
    wikipedia_title: str | None = Field(
        description="Exact title of the English Wikipedia article about this landmark, or null if unsure."
    )
    matches_candidate: bool = Field(description="True if the landmark is one of the given candidates.")
    confidence: Literal["high", "medium", "low"] = Field(
        description="high only if you clearly recognize this exact landmark; low if you are guessing."
    )
    reason: str = Field(description="One short sentence in Bulgarian describing what is in the photo.")


class GeminiResult(GeminiVerdict):
    model: str = Field(description="Gemini моделът, който е отговорил")


class Verification(BaseModel):
    needed: bool = Field(description="Дали резултатът е бил пратен за проверка")
    reasons: list[str] = Field(description="Защо локалният модел е сметнат за несигурен")
    status: VerificationStatus
    gemini: GeminiResult | None = Field(None, description="Приетият отговор на Gemini")
    answers: list[GeminiResult] = Field([], description="Всички отговори на Gemini моделите")
    agreement: Literal["all", "single"] | None = Field(
        None, description="all = всички отговорили модели са съгласни, single = отговорил е само един"
    )
    error: str | None = None


class PredictResponse(BaseModel):
    source: str = Field(description="Името на качения файл или URL-ът на снимката")
    landmark: Landmark
    info: LandmarkInfo
    candidates: list[Candidate] = Field(description="Суровите предложения на локалния модел")
    verification: Verification


class HealthResponse(BaseModel):
    status: Literal["ok"]
    model_loaded: bool
    landmarks_known: int
    gemini_enabled: bool
    gemini_models: list[str]
