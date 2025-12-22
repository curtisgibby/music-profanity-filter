"""
Transcription module using OpenAI Whisper.

Transcribes vocals and provides word-level timestamps.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import whisper


@dataclass
class TranscribedWord:
    """A single transcribed word with timing information."""

    word: str
    start: float  # Start time in seconds
    end: float  # End time in seconds
    confidence: float = 1.0

    def __repr__(self) -> str:
        return f"TranscribedWord('{self.word}', {self.start:.2f}s-{self.end:.2f}s)"


def normalize_word(word: str) -> str:
    """Normalize a word for comparison (lowercase, remove punctuation)."""
    return re.sub(r"[^\w]", "", word.lower())


def parse_lyrics(lyrics_text: str) -> list[str]:
    """Parse lyrics text into a list of words."""
    # Remove section headers like [Verse 1], [Chorus], etc.
    text = re.sub(r"\[.*?\]", "", lyrics_text)
    # Split into words and filter empty
    words = text.split()
    return [w for w in words if w.strip()]


class Transcriber:
    """Transcribes audio using Whisper with word-level timestamps."""

    def __init__(self, model_size: str = "base"):
        """
        Initialize the transcriber.

        Args:
            model_size: Whisper model size. Options: tiny, base, small, medium, large
                       Larger models are more accurate but slower.
        """
        self.model_size = model_size
        self._model = None

    @property
    def model(self):
        """Lazy-load the Whisper model."""
        if self._model is None:
            print(f"Loading Whisper {self.model_size} model...")
            self._model = whisper.load_model(self.model_size)
        return self._model

    def transcribe(self, audio_path: Path) -> list[TranscribedWord]:
        """
        Transcribe an audio file and return word-level timestamps.

        Args:
            audio_path: Path to the audio file (vocals preferred)

        Returns:
            List of TranscribedWord objects with timing information
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        print(f"Transcribing {audio_path.name}...")

        # Transcribe with word timestamps
        result = self.model.transcribe(
            str(audio_path),
            word_timestamps=True,
            language="en",  # Assume English for profanity detection
        )

        words = []
        for segment in result.get("segments", []):
            for word_info in segment.get("words", []):
                word = TranscribedWord(
                    word=word_info["word"].strip(),
                    start=word_info["start"],
                    end=word_info["end"],
                    confidence=word_info.get("probability", 1.0),
                )
                words.append(word)

        print(f"Transcribed {len(words)} words")
        return words

    def transcribe_with_context(
        self, audio_path: Path, reference_lyrics: str | None = None
    ) -> list[TranscribedWord]:
        """
        Transcribe audio, optionally using reference lyrics for improved accuracy.

        Args:
            audio_path: Path to the audio file
            reference_lyrics: Optional published lyrics to guide transcription

        Returns:
            List of TranscribedWord objects
        """
        # Get Whisper's transcription with timestamps
        transcribed_words = self.transcribe(audio_path)

        if not reference_lyrics:
            return transcribed_words

        print("Aligning transcription with reference lyrics...")

        # Parse reference lyrics into words
        ref_words = parse_lyrics(reference_lyrics)

        # Normalize both word lists for comparison
        transcribed_normalized = [normalize_word(w.word) for w in transcribed_words]
        ref_normalized = [normalize_word(w) for w in ref_words]

        # Use SequenceMatcher to find alignment between transcribed and reference
        matcher = SequenceMatcher(None, transcribed_normalized, ref_normalized)

        # Build aligned output: reference words with timestamps from transcription
        aligned_words = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                # Words match - use reference word with transcribed timestamp
                for t_idx, r_idx in zip(range(i1, i2), range(j1, j2)):
                    aligned_words.append(
                        TranscribedWord(
                            word=ref_words[r_idx],
                            start=transcribed_words[t_idx].start,
                            end=transcribed_words[t_idx].end,
                            confidence=transcribed_words[t_idx].confidence,
                        )
                    )
            elif tag == "replace":
                # Words differ - use reference words with interpolated timestamps
                t_words = transcribed_words[i1:i2]
                r_words_slice = ref_words[j1:j2]

                if t_words:
                    start_time = t_words[0].start
                    end_time = t_words[-1].end
                    duration = end_time - start_time

                    # Interpolate timestamps across reference words
                    for idx, ref_word in enumerate(r_words_slice):
                        word_start = start_time + (duration * idx / len(r_words_slice))
                        word_end = start_time + (duration * (idx + 1) / len(r_words_slice))
                        aligned_words.append(
                            TranscribedWord(
                                word=ref_word,
                                start=word_start,
                                end=word_end,
                                confidence=0.5,  # Lower confidence for interpolated
                            )
                        )
            elif tag == "insert":
                # Reference has words that weren't transcribed - interpolate
                if aligned_words:
                    # Use timing from nearby words
                    last_end = aligned_words[-1].end
                    # Estimate ~0.3s per word
                    for idx, ref_word in enumerate(ref_words[j1:j2]):
                        aligned_words.append(
                            TranscribedWord(
                                word=ref_word,
                                start=last_end + (idx * 0.3),
                                end=last_end + ((idx + 1) * 0.3),
                                confidence=0.3,  # Low confidence for inserted
                            )
                        )
            # 'delete' - transcribed words not in reference - skip them

        print(f"Aligned {len(aligned_words)} words from reference lyrics")
        return aligned_words
