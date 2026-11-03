import pytest

from yaku.loader import load_mask_rules, load_passthrough, load_source, load_target
from yaku.types import SourceProfile, TargetProfile


@pytest.fixture
def english() -> SourceProfile:
    return load_source("en")


@pytest.fixture
def japanese() -> TargetProfile:
    return load_target("ja")


@pytest.fixture
def mask_rules():
    return load_mask_rules()


@pytest.fixture
def passthrough():
    return load_passthrough()
