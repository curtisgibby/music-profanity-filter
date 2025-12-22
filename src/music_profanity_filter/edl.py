"""
EDL (Edit Decision List) module.

Handles reading/writing EDL files for manual timestamp correction.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def format_timestamp(seconds: float) -> str:
    """
    Format seconds as M:SS.mm for human-readable display.

    Examples:
        0.5 -> "0:00.50"
        72.86 -> "1:12.86"
        185.5 -> "3:05.50"
    """
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}:{secs:05.2f}"


def parse_timestamp(timestamp: str) -> float:
    """
    Parse a human-readable timestamp back to seconds.

    Supports formats:
        "1:12.86" -> 72.86
        "01:12.86" -> 72.86
        "72.86" -> 72.86 (raw seconds as fallback)
        "1:05:30.50" -> 3930.5 (hours:minutes:seconds)
    """
    timestamp = timestamp.strip()

    # Try to parse as float first (raw seconds)
    try:
        return float(timestamp)
    except ValueError:
        pass

    # Parse M:SS.mm or MM:SS.mm or H:MM:SS.mm format
    parts = timestamp.split(":")
    if len(parts) == 2:
        # M:SS.mm or MM:SS.mm
        minutes = int(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds
    elif len(parts) == 3:
        # H:MM:SS.mm
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    else:
        raise ValueError(f"Cannot parse timestamp: {timestamp}")


@dataclass
class EditPoint:
    """A single edit point (profanity to mute)."""

    start: float
    end: float
    word: str
    confidence: float = 1.0

    def to_dict(self) -> dict:
        """Convert to dict with human-readable timestamps."""
        return {
            "start": format_timestamp(self.start),
            "end": format_timestamp(self.end),
            "word": self.word,
            "confidence": round(self.confidence, 3),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EditPoint":
        """Parse from dict, accepting both human-readable and raw timestamps."""
        return cls(
            start=parse_timestamp(str(data["start"])),
            end=parse_timestamp(str(data["end"])),
            word=data["word"],
            confidence=float(data.get("confidence", 1.0)),
        )


@dataclass
class EDL:
    """Edit Decision List for a song."""

    source_file: str
    generated: str
    stems_dir: str | None
    edits: list[EditPoint]

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "generated": self.generated,
            "stems_dir": self.stems_dir,
            "edits": [e.to_dict() for e in self.edits],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EDL":
        return cls(
            source_file=data["source_file"],
            generated=data["generated"],
            stems_dir=data.get("stems_dir"),
            edits=[EditPoint.from_dict(e) for e in data["edits"]],
        )

    def save(self, path: Path) -> None:
        """Save EDL to a JSON file."""
        path = Path(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        print(f"EDL saved to: {path}")

    @classmethod
    def load(cls, path: Path) -> "EDL":
        """Load EDL from a JSON file."""
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


def create_edl(
    source_file: Path,
    profanities: list,
    stems_dir: Path | None = None,
) -> EDL:
    """
    Create an EDL from detected profanities.

    Args:
        source_file: Path to the original audio file
        profanities: List of ProfanityMatch objects
        stems_dir: Optional path to stems directory for re-use

    Returns:
        EDL object
    """
    edits = [
        EditPoint(
            start=p.start,
            end=p.end,
            word=p.original_word,
            confidence=p.confidence,
        )
        for p in profanities
    ]

    return EDL(
        source_file=str(source_file),
        generated=datetime.now().isoformat(),
        stems_dir=str(stems_dir) if stems_dir else None,
        edits=edits,
    )
