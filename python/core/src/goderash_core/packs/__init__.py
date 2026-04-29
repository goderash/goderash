"""Compliance pack generators."""

from .base import Artifact, PackGenerator
from .ffiec import FfiecPackGenerator
from .finra import FinraPackGenerator, Sec17a4PackGenerator
from .hipaa import HipaaPackGenerator
from .soc2 import Soc2PackGenerator

__all__ = [
    "Artifact",
    "FfiecPackGenerator",
    "FinraPackGenerator",
    "HipaaPackGenerator",
    "PackGenerator",
    "Sec17a4PackGenerator",
    "Soc2PackGenerator",
]


PACK_REGISTRY: dict[str, type[PackGenerator]] = {
    "soc2": Soc2PackGenerator,
    "hipaa": HipaaPackGenerator,
    "ffiec": FfiecPackGenerator,
    "finra": FinraPackGenerator,
    "sec_17a4": Sec17a4PackGenerator,
}
