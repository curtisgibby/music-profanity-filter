"""
Audio editing module.

Handles muting profanity in vocal tracks and recombining with instrumentals.
"""

from pathlib import Path

from pydub import AudioSegment

from .detector import ProfanityMatch


class AudioEditor:
    """Edits audio tracks to remove profanity."""

    def __init__(self, fade_ms: int = 10):
        """
        Initialize the audio editor.

        Args:
            fade_ms: Milliseconds of fade in/out around muted sections
                    to avoid harsh cuts.
        """
        self.fade_ms = fade_ms

    def mute_sections(
        self,
        audio_path: Path,
        sections: list[tuple[float, float]],
        output_path: Path | None = None,
    ) -> Path:
        """
        Mute specific time sections in an audio file.

        Args:
            audio_path: Path to the input audio file
            sections: List of (start_seconds, end_seconds) tuples to mute
            output_path: Path for output file. If None, modifies in place.

        Returns:
            Path to the edited audio file
        """
        audio_path = Path(audio_path)
        audio = AudioSegment.from_file(str(audio_path))

        if output_path is None:
            output_path = audio_path

        # Sort sections by start time
        sections = sorted(sections, key=lambda x: x[0])

        # Process sections from end to start to maintain timing accuracy
        for start_sec, end_sec in reversed(sections):
            start_ms = int(start_sec * 1000)
            end_ms = int(end_sec * 1000)

            # Clamp to audio bounds
            start_ms = max(0, start_ms - self.fade_ms)
            end_ms = min(len(audio), end_ms + self.fade_ms)

            # Create silent segment
            duration_ms = end_ms - start_ms
            silence = AudioSegment.silent(duration=duration_ms)

            # Replace section with silence
            audio = audio[:start_ms] + silence + audio[end_ms:]

        # Export
        output_path = Path(output_path)
        audio.export(str(output_path), format=output_path.suffix.lstrip("."))

        return output_path

    def mute_profanities(
        self,
        vocals_path: Path,
        profanities: list[ProfanityMatch],
        output_path: Path | None = None,
    ) -> Path:
        """
        Mute profanities in a vocal track.

        Args:
            vocals_path: Path to the vocal track
            profanities: List of ProfanityMatch objects with timing info
            output_path: Path for output file

        Returns:
            Path to the edited vocal track
        """
        sections = [(p.start, p.end) for p in profanities]
        return self.mute_sections(vocals_path, sections, output_path)

    def combine_stems(
        self,
        vocals_path: Path,
        instrumentals_path: Path,
        output_path: Path,
        output_format: str = "mp3",
        bitrate: str = "320k",
    ) -> Path:
        """
        Combine vocal and instrumental stems into a single track.

        Args:
            vocals_path: Path to the (edited) vocal track
            instrumentals_path: Path to the instrumental track
            output_path: Path for the combined output file
            output_format: Output audio format (mp3, wav, flac, etc.)
            bitrate: Bitrate for compressed formats

        Returns:
            Path to the combined audio file
        """
        print("Combining stems...")

        vocals = AudioSegment.from_file(str(vocals_path))
        instrumentals = AudioSegment.from_file(str(instrumentals_path))

        # Ensure both tracks are the same length
        # (they should be, but handle edge cases)
        if len(vocals) != len(instrumentals):
            # Pad the shorter one with silence
            diff = len(vocals) - len(instrumentals)
            if diff > 0:
                instrumentals += AudioSegment.silent(duration=diff)
            else:
                vocals += AudioSegment.silent(duration=-diff)

        # Overlay vocals on instrumentals
        combined = instrumentals.overlay(vocals)

        # Export
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        export_params = {"format": output_format}
        if output_format in ("mp3", "ogg"):
            export_params["bitrate"] = bitrate

        combined.export(str(output_path), **export_params)

        print(f"Saved combined track to {output_path}")
        return output_path
