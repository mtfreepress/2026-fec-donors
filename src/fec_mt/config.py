from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    cycle: int = 2026
    state: str = "MT"
    offices: tuple[str, ...] = field(default_factory=lambda: ("H", "S"))
    start_date: date | None = None
    end_date: date | None = None
    output_dir: Path = Path("data")
    refresh: bool = False

    def __post_init__(self) -> None:
        if self.cycle < 1980 or self.cycle % 2:
            raise ValueError("cycle must be an even-numbered election year")
        state = self.state.strip().upper()
        offices = tuple(dict.fromkeys(office.strip().upper() for office in self.offices))
        if len(state) != 2:
            raise ValueError("state must be a two-letter postal abbreviation")
        if not offices or not set(offices) <= {"H", "S", "P"}:
            raise ValueError("office must be H, S, or explicitly enabled P")
        start = self.start_date or date(self.cycle - 1, 1, 1)
        if self.end_date and self.end_date < start:
            raise ValueError("end date cannot precede start date")
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "offices", offices)
        object.__setattr__(self, "start_date", start)
        object.__setattr__(self, "output_dir", Path(self.output_dir))

    @property
    def cycle_suffix(self) -> str:
        return str(self.cycle)[-2:]

    @property
    def raw_dir(self) -> Path:
        return self.output_dir / "raw"

    @property
    def intermediate_dir(self) -> Path:
        return self.output_dir / "intermediate"

    @property
    def final_dir(self) -> Path:
        return self.output_dir / "output"

    @property
    def cache_dir(self) -> Path:
        return self.raw_dir / "cache"

    def create_directories(self) -> None:
        for path in (self.raw_dir, self.intermediate_dir, self.final_dir, self.cache_dir):
            path.mkdir(parents=True, exist_ok=True)

