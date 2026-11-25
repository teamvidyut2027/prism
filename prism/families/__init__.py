from .bars import BarChartFamily
from .base import Family, VerifyError
from .clocks import ClockFamily
from .lines import LineChartFamily
from .mazes import MazeFamily
from .shapes import ShapeSceneFamily
from .tables import TableFamily

REGISTRY: dict[str, Family] = {f.name: f for f in (
    BarChartFamily(), LineChartFamily(), ShapeSceneFamily(), ClockFamily(), MazeFamily(), TableFamily())}


def get(name: str) -> Family:
    return REGISTRY[name]


__all__ = ["REGISTRY", "get", "Family", "VerifyError"]
