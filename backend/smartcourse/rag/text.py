from __future__ import annotations

import math
import re
import unicodedata


LATIN_TOKEN = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*", re.IGNORECASE)
CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value)).lower()
    return re.sub(r"\s+", " ", value).strip()


def tokenize(value: str) -> list[str]:
    normalized = normalize_text(value)
    tokens = LATIN_TOKEN.findall(normalized)
    for run in CJK_RUN.findall(normalized):
        tokens.extend(run)
        tokens.extend(run[index:index + 2] for index in range(len(run) - 1))
    return [token for token in tokens if token]


def projected_vector(value: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    normalized = normalize_text(value)
    features = tokenize(normalized)
    compact = re.sub(r"\s+", "", normalized)
    features.extend(compact[index:index + 3] for index in range(max(0, len(compact) - 2)))
    for feature in features:
        if not feature:
            continue
        position = sum((index + 1) * ord(char) for index, char in enumerate(feature)) % dimensions
        direction = -1.0 if sum(ord(char) for char in feature) % 2 else 1.0
        vector[position] += direction * (1.0 + math.log1p(len(feature)))
    length = math.sqrt(sum(item * item for item in vector)) or 1.0
    return [item / length for item in vector]


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))
