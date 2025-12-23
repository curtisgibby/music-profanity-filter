"""
Main pipeline module.

Orchestrates the full profanity filtering workflow.
"""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .detector import ProfanityDetector, ProfanityMatch
from .edl import EDL, EditPoint, create_edl
from .editor import AudioEditor
from .metadata import copy_tags, embed_synced_lyrics, write_edit_log
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
    edl_path: Path | None = None  # Path to generated EDL file
    stems_dir: Path | None = None  # Path to stems directory for re-use


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

        # Determine step count based on whether lyrics are provided
        total_steps = 6 if lyrics else 5
        step = 0

        # Early check: if we have lyrics, scan them for profanity first
        # This avoids expensive Demucs processing if there's nothing to filter
        if lyrics:
            step += 1
            print(f"\n[{step}/{total_steps}] Checking lyrics for profanity...")
            profanity_in_lyrics = self.detector.check_text(lyrics)
            if not profanity_in_lyrics:
                print("\nNo profanity found in lyrics - nothing to do.")
                return FilterResult(
                    input_path=input_path,
                    output_path=None,
                    profanities_found=[],
                    transcribed_words=[],
                    success=True,
                )
            print(f"Found potential profanity in lyrics: {', '.join(profanity_in_lyrics)}")
            print("Proceeding with audio processing...")

        # Create temp directory for intermediate files
        temp_dir = Path(tempfile.mkdtemp(prefix="music_filter_"))

        try:
            # Separate stems
            step += 1
            print(f"\n[{step}/{total_steps}] Separating stems from {input_path.name}...")
            stems = self.separator.separate(input_path, output_dir=temp_dir)
            vocals_path = stems["vocals"]
            instrumentals_path = stems["instrumentals"]

            # Transcribe vocals
            step += 1
            print(f"\n[{step}/{total_steps}] Transcribing vocals...")
            if lyrics:
                words = self.transcriber.transcribe_with_context(vocals_path, lyrics)
            else:
                words = self.transcriber.transcribe(vocals_path)

            # Detect profanity
            step += 1
            print(f"\n[{step}/{total_steps}] Detecting profanity...")
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

            # Edit vocals (mute profanity)
            step += 1
            print(f"\n[{step}/{total_steps}] Muting {len(profanities)} profanities in vocals...")
            edited_vocals_path = temp_dir / "edited_vocals.wav"
            self.editor.mute_profanities(vocals_path, profanities, edited_vocals_path)

            # Recombine and export
            step += 1
            print(f"\n[{step}/{total_steps}] Combining stems and exporting...")
            output_format = output_path.suffix.lstrip(".") or "mp3"
            self.editor.combine_stems(
                edited_vocals_path,
                instrumentals_path,
                output_path,
                output_format=output_format,
            )

            # Copy metadata and embed synced lyrics
            print(f"\nCopying metadata...")
            copy_tags(input_path, output_path)
            if words and output_path.suffix.lower() == ".mp3":
                embed_synced_lyrics(output_path, words)

            # Log the edits
            write_edit_log(input_path, profanities)

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

    def generate_edl(
        self,
        input_path: Path | str,
        edl_path: Path | str | None = None,
        stems_dir: Path | str | None = None,
        lyrics: str | None = None,
    ) -> FilterResult:
        """
        Generate an EDL file with detected profanities and save stems for later.

        This allows users to review/edit timestamps before applying the filter.

        Args:
            input_path: Path to the input audio file
            edl_path: Path for the EDL file. If None, uses "{input}.edl.json"
            stems_dir: Directory to save stems. If None, creates alongside input file.
            lyrics: Optional reference lyrics for improved detection.

        Returns:
            FilterResult with edl_path and stems_dir set
        """
        input_path = Path(input_path)
        if not input_path.exists():
            return FilterResult(
                input_path=input_path,
                output_path=None,
                profanities_found=[],
                transcribed_words=[],
                success=False,
                error=f"Input file not found: {input_path}",
            )

        # Determine EDL path
        if edl_path is None:
            edl_path = input_path.parent / f"{input_path.stem}.edl.json"
        else:
            edl_path = Path(edl_path)

        # Determine stems directory
        if stems_dir is None:
            stems_dir = input_path.parent / f"{input_path.stem}_stems"
        else:
            stems_dir = Path(stems_dir)
        stems_dir.mkdir(parents=True, exist_ok=True)

        # Early check for profanity in lyrics
        if lyrics:
            print(f"\n[1/4] Checking lyrics for profanity...")
            profanity_in_lyrics = self.detector.check_text(lyrics)
            if not profanity_in_lyrics:
                print("\nNo profanity found in lyrics - nothing to do.")
                return FilterResult(
                    input_path=input_path,
                    output_path=None,
                    profanities_found=[],
                    transcribed_words=[],
                    success=True,
                )
            print(f"Found potential profanity: {', '.join(profanity_in_lyrics)}")
            step_offset = 1
            total_steps = 4
        else:
            step_offset = 0
            total_steps = 3

        try:
            # Separate stems
            print(f"\n[{step_offset + 1}/{total_steps}] Separating stems...")
            stems = self.separator.separate(input_path, output_dir=stems_dir)

            # Transcribe
            print(f"\n[{step_offset + 2}/{total_steps}] Transcribing vocals...")
            if lyrics:
                words = self.transcriber.transcribe_with_context(stems["vocals"], lyrics)
            else:
                words = self.transcriber.transcribe(stems["vocals"])

            # Detect profanity
            print(f"\n[{step_offset + 3}/{total_steps}] Detecting profanity...")
            profanities = self.detector.detect(words)

            if not profanities:
                print("\nNo profanity detected - nothing to do.")
                # Clean up stems if no profanity
                shutil.rmtree(stems_dir)
                return FilterResult(
                    input_path=input_path,
                    output_path=None,
                    profanities_found=[],
                    transcribed_words=words,
                    success=True,
                )

            # Create and save EDL
            edl = create_edl(input_path, profanities, stems_dir)
            edl.save(edl_path)

            print(f"\nEDL generated with {len(profanities)} edit points.")
            print(f"  EDL file: {edl_path}")
            print(f"  Stems directory: {stems_dir}")
            print("\nReview the EDL file, adjust timestamps if needed, then run:")
            print(f"  music-clean {input_path.name} --apply-edl {edl_path.name}")

            return FilterResult(
                input_path=input_path,
                output_path=None,
                profanities_found=profanities,
                transcribed_words=words,
                success=True,
                edl_path=edl_path,
                stems_dir=stems_dir,
            )

        except Exception as e:
            return FilterResult(
                input_path=input_path,
                output_path=None,
                profanities_found=[],
                transcribed_words=[],
                success=False,
                error=str(e),
            )

    def apply_edl(
        self,
        input_path: Path | str,
        edl_path: Path | str,
        output_path: Path | str | None = None,
        overwrite: bool = False,
    ) -> FilterResult:
        """
        Apply edits from an EDL file to create a cleaned track.

        Re-uses stems from the EDL if available.

        Args:
            input_path: Path to the input audio file
            edl_path: Path to the EDL file
            output_path: Path for the cleaned output. If None, creates "(clean)" version.
            overwrite: If True, overwrites the original file

        Returns:
            FilterResult with details about the operation
        """
        input_path = Path(input_path)
        edl_path = Path(edl_path)

        if not input_path.exists():
            return FilterResult(
                input_path=input_path,
                output_path=None,
                profanities_found=[],
                transcribed_words=[],
                success=False,
                error=f"Input file not found: {input_path}",
            )

        if not edl_path.exists():
            return FilterResult(
                input_path=input_path,
                output_path=None,
                profanities_found=[],
                transcribed_words=[],
                success=False,
                error=f"EDL file not found: {edl_path}",
            )

        # Determine output path
        if output_path is None:
            if overwrite:
                output_path = input_path
            else:
                output_path = input_path.parent / f"{input_path.stem} (clean){input_path.suffix}"
        else:
            output_path = Path(output_path)

        try:
            # Load EDL
            print(f"\n[1/3] Loading EDL from {edl_path.name}...")
            edl = EDL.load(edl_path)

            if not edl.edits:
                print("\nNo edits in EDL file - nothing to do.")
                return FilterResult(
                    input_path=input_path,
                    output_path=None,
                    profanities_found=[],
                    transcribed_words=[],
                    success=True,
                )

            # Check for existing stems
            stems_dir = Path(edl.stems_dir) if edl.stems_dir else None
            vocals_path = None
            instrumentals_path = None

            if stems_dir and stems_dir.exists():
                # Look for vocals and instrumentals in stems directory
                possible_vocals = list(stems_dir.glob("**/vocals.wav"))
                possible_instrumentals = list(stems_dir.glob("**/no_vocals.wav"))

                if possible_vocals and possible_instrumentals:
                    vocals_path = possible_vocals[0]
                    instrumentals_path = possible_instrumentals[0]
                    print(f"  Re-using stems from: {stems_dir}")

            # If no stems found, we need to separate again
            temp_dir = None
            if vocals_path is None:
                print(f"\n[1/3] Separating stems (no cached stems found)...")
                temp_dir = Path(tempfile.mkdtemp(prefix="music_filter_"))
                stems = self.separator.separate(input_path, output_dir=temp_dir)
                vocals_path = stems["vocals"]
                instrumentals_path = stems["instrumentals"]

            # Convert EDL edits to ProfanityMatch-like objects for the editor
            edits_for_muting = [
                ProfanityMatch(
                    word=e.word,
                    original_word=e.word,
                    start=e.start,
                    end=e.end,
                    confidence=e.confidence,
                )
                for e in edl.edits
            ]

            # Mute profanities
            print(f"\n[2/3] Muting {len(edits_for_muting)} edit points in vocals...")
            edit_temp_dir = temp_dir or Path(tempfile.mkdtemp(prefix="music_filter_edit_"))
            edited_vocals_path = edit_temp_dir / "edited_vocals.wav"
            self.editor.mute_profanities(vocals_path, edits_for_muting, edited_vocals_path)

            # Combine and export
            print(f"\n[3/3] Combining stems and exporting...")
            output_format = output_path.suffix.lstrip(".") or "mp3"
            self.editor.combine_stems(
                edited_vocals_path,
                instrumentals_path,
                output_path,
                output_format=output_format,
            )

            # Copy metadata
            print(f"\nCopying metadata...")
            copy_tags(input_path, output_path)

            # Log the edits
            write_edit_log(input_path, edits_for_muting)

            print(f"\nDone! Cleaned track saved to: {output_path}")

            return FilterResult(
                input_path=input_path,
                output_path=output_path,
                profanities_found=edits_for_muting,
                transcribed_words=[],
                success=True,
            )

        except Exception as e:
            return FilterResult(
                input_path=input_path,
                output_path=None,
                profanities_found=[],
                transcribed_words=[],
                success=False,
                error=str(e),
            )

        finally:
            # Cleanup temp files (but not cached stems)
            if temp_dir and temp_dir.exists() and not self.keep_temp_files:
                shutil.rmtree(temp_dir)
