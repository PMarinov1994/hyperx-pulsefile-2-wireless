import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import click

from pulsefire.colors import Rgb
from pulsefire.protocol import DpiStage, LiftOff, PollingRate

SETTINGS_FILE = Path(click.get_app_dir("pulsefire")) / "settings.json"


def _default_stages() -> list[DpiStage]:
    return [
        DpiStage(400, Rgb(0xFF, 0x00, 0x00)),
        DpiStage(800, Rgb(0x00, 0x00, 0xFF)),
        DpiStage(1600, Rgb(0xFF, 0xFF, 0x00)),
        DpiStage(3200, Rgb(0x00, 0xFF, 0x00)),
        DpiStage(6400, Rgb(0xFF, 0xFF, 0xFF)),
    ]


@dataclass(frozen=True)
class Settings:
    stages: list[DpiStage] = field(default_factory=_default_stages)
    active_stage: int = 2
    polling_rate: PollingRate = PollingRate.HZ_1000
    lift_off: LiftOff = LiftOff.LOW
    brightness: int = 100

    def to_json(self) -> dict[str, Any]:
        return {
            "stages": [{"dpi": stage.dpi, "color": stage.color.hex} for stage in self.stages],
            "active_stage": self.active_stage,
            "polling_rate": int(self.polling_rate),
            "lift_off": self.lift_off.name.lower(),
            "brightness": self.brightness,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        stages = [
            DpiStage(int(item["dpi"]), Rgb.parse(str(item["color"]))) for item in data["stages"]
        ]
        return cls(
            stages=stages,
            active_stage=int(data["active_stage"]),
            polling_rate=PollingRate(int(data["polling_rate"])),
            lift_off=LiftOff[str(data["lift_off"]).upper()],
            brightness=int(data["brightness"]),
        )


def load_settings(path: Path = SETTINGS_FILE) -> Settings:
    if not path.exists():
        return Settings()
    return Settings.from_json(json.loads(path.read_text()))


def save_settings(settings: Settings, path: Path = SETTINGS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings.to_json(), indent=2) + "\n")
