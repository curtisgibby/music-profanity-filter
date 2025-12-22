"""
Stem separation module using Demucs.

Separates audio into vocals and instrumentals for targeted editing.
"""

import subprocess
import tempfile
from pathlib import Path

from tqdm import tqdm


class StemSeparator:
    """Separates audio tracks into vocal and instrumental stems using Demucs."""

    def __init__(self, model: str = "htdemucs"):
        """
        Initialize the stem separator.

        Args:
            model: Demucs model to use. Options: htdemucs, htdemucs_ft, mdx_extra
        """
        self.model = model

    def separate(self, audio_path: Path, output_dir: Path | None = None) -> dict[str, Path]:
        """
        Separate an audio file into stems.

        Args:
            audio_path: Path to the input audio file
            output_dir: Directory to save stems. If None, uses a temp directory.

        Returns:
            Dictionary with 'vocals' and 'instrumentals' paths
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp(prefix="music_filter_"))
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        print(f"Separating stems using {self.model}...")

        # Run demucs
        cmd = [
            "python", "-m", "demucs",
            "--two-stems", "vocals",  # Only separate vocals vs rest
            "-n", self.model,
            "-o", str(output_dir),
            str(audio_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Demucs failed: {result.stderr}")

        # Demucs outputs to: output_dir/model_name/track_name/{vocals,no_vocals}.wav
        stem_dir = output_dir / self.model / audio_path.stem

        vocals_path = stem_dir / "vocals.wav"
        instrumentals_path = stem_dir / "no_vocals.wav"

        if not vocals_path.exists() or not instrumentals_path.exists():
            raise RuntimeError(f"Expected stem files not found in {stem_dir}")

        print(f"Stems saved to {stem_dir}")

        return {
            "vocals": vocals_path,
            "instrumentals": instrumentals_path,
        }
