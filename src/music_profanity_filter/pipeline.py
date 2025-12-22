"""
Main pipeline module.

Orchestrates the full profanity filtering workflow.
"""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .detector import ProfanityDetector, ProfanityMatch
from .editor import AudioEditor
from .metadata import copy_tags, embed_synced_lyrics
from .separator import StemSeparator
from .transcriber import Transcriber, TranscribedWord


@dataclass
class FilterResult:
    """Result of the profanity filtering process."""

    input_path: Path
    output_path: Path | None  # None if no profanity found (no file created)
    profanities_found: list[ProfanityMatch]
    transcribed_words: list[TranscribedWord]
    success: bool
    error: str | None = None


class MusicProfanityFilter:
    """
    Main class for filtering profanity from music tracks.

    Orchestrates stem separation, transcription, detection, and editing.
    """

    def __init__(
        self,
        demucs_model: str = "htdemucs",
        whisper_model: str = "base",
        profanity_list_path: Path | None = None,
        keep_temp_files: bool = False,
    ):
        """
        Initialize the music profanity filter.

        Args:
            demucs_model: Demucs model for stem separation
            whisper_model: Whisper model size for transcription
            profanity_list_path: Path to custom profanity word list
            keep_temp_files: If True, don't delete intermediate files
        """
        self.separator = StemSeparator(model=demucs_model)
        self.transcriber = Transcriber(model_size=whisper_model)
        self.detector = ProfanityDetector(word_list_path=profanity_list_path)
        self.editor = AudioEditor()
        self.keep_temp_files = keep_temp_files

    def filter(
        self,
        input_path: Path | str,
        output_path: Path | str | None = None,
        overwrite: bool = False,
        preview_callback: callable = None,
        lyrics: str | None = None,
    ) -> FilterResult:
        """
        Filter profanity from a music track.

        Args:
            input_path: Path to the input audio file
            output_path: Path for the cleaned output. If None, creates "(clean)" version.
            overwrite: If True and output_path is None, overwrites the original file
            preview_callback: Optional callback function that receives profanities list.
                             Should return True to proceed, False to cancel.
            lyrics: Optional reference lyrics text for improved alignment accuracy.

        Returns:
            FilterResult with details about the operation
        """
        input_path = Path(input_path)
        if not input_path.exists():
            return FilterResult(
                input_path=input_path,
                output_path=Path(""),
                profanities_found=[],
                transcribed_words=[],
                success=False,
                error=f"Input file not found: {input_path}",
            )

        # Determine output path
        if output_path is None:
            if overwrite:
                output_path = input_path
            else:
                output_path = input_path.parent / f"{input_path.stem} (clean){input_path.suffix}"
        else:
            output_path = Path(output_path)

        # Create temp directory for intermediate files
        temp_dir = Path(tempfile.mkdtemp(prefix="music_filter_"))

        try:
            # Step 1: Separate stems
            print(f"\n[1/6] Separating stems from {input_path.name}...")
            stems = self.separator.separate(input_path, output_dir=temp_dir)
            vocals_path = stems["vocals"]
            instrumentals_path = stems["instrumentals"]

            # Step 2: Transcribe vocals
            print(f"\n[2/6] Transcribing vocals...")
            if lyrics:
                words = self.transcriber.transcribe_with_context(vocals_path, lyrics)
            else:
                words = self.transcriber.transcribe(vocals_path)

            # Step 3: Detect profanity
            print(f"\n[3/6] Detecting profanity...")
            profanities = self.detector.detect(words)

            # Preview callback if provided
            if preview_callback and profanities:
                if not preview_callback(profanities):
                    return FilterResult(
                        input_path=input_path,
                        output_path=output_path,
                        profanities_found=profanities,
                        transcribed_words=words,
                        success=False,
                        error="Cancelled by user",
                    )

            if not profanities:
                print("\nNo profanity detected - nothing to do.")
                return FilterResult(
                    input_path=input_path,
                    output_path=None,
                    profanities_found=[],
                    transcribed_words=words,
                    success=True,
                )

            # Step 4: Edit vocals (mute profanity)
            print(f"\n[4/6] Muting {len(profanities)} profanities in vocals...")
            edited_vocals_path = temp_dir / "edited_vocals.wav"
            self.editor.mute_profanities(vocals_path, profanities, edited_vocals_path)

            # Step 5: Recombine and export
            print(f"\n[5/6] Combining stems and exporting...")
            output_format = output_path.suffix.lstrip(".") or "mp3"
            self.editor.combine_stems(
                edited_vocals_path,
                instrumentals_path,
                output_path,
                output_format=output_format,
            )

            # Step 6: Copy metadata and embed synced lyrics
            print(f"\n[6/6] Copying metadata...")
            copy_tags(input_path, output_path)
            if words and output_path.suffix.lower() == ".mp3":
                embed_synced_lyrics(output_path, words)

            print(f"\nDone! Cleaned track saved to: {output_path}")

            return FilterResult(
                input_path=input_path,
                output_path=output_path,
                profanities_found=profanities,
                transcribed_words=words,
                success=True,
            )

        except Exception as e:
            return FilterResult(
                input_path=input_path,
                output_path=output_path,
                profanities_found=[],
                transcribed_words=[],
                success=False,
                error=str(e),
            )

        finally:
            # Cleanup temp files
            if not self.keep_temp_files and temp_dir.exists():
                shutil.rmtree(temp_dir)

    def detect_only(self, input_path: Path | str) -> list[ProfanityMatch]:
        """
        Only detect profanity without editing (faster, useful for preview).

        This still requires stem separation for accurate transcription.

        Args:
            input_path: Path to the input audio file

        Returns:
            List of detected ProfanityMatch objects
        """
        input_path = Path(input_path)
        temp_dir = Path(tempfile.mkdtemp(prefix="music_filter_"))

        try:
            # Separate stems
            stems = self.separator.separate(input_path, output_dir=temp_dir)

            # Transcribe
            words = self.transcriber.transcribe(stems["vocals"])

            # Detect
            return self.detector.detect(words)

        finally:
            if not self.keep_temp_files:
                shutil.rmtree(temp_dir)
