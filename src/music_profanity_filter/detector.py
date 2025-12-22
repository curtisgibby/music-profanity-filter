"""
Profanity detection module.

Identifies profane words in transcribed text using a configurable word list.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from .transcriber import TranscribedWord


@dataclass
class ProfanityMatch:
    """A detected profanity with timing information."""

    word: str
    original_word: str  # The word as transcribed (may have different casing)
    start: float
    end: float
    confidence: float

    def __repr__(self) -> str:
        return f"ProfanityMatch('{self.word}', {self.start:.2f}s-{self.end:.2f}s)"


class ProfanityDetector:
    """Detects profanity in transcribed words."""

    def __init__(self, word_list_path: Path | None = None):
        """
        Initialize the profanity detector.

        Args:
            word_list_path: Path to a text file with profane words (one per line).
                           If None, uses the built-in default list.
        """
        self.profanity_set: set[str] = set()
        self._load_word_list(word_list_path)

    def _load_word_list(self, word_list_path: Path | None = None) -> None:
        """Load profanity words from a file."""
        if word_list_path is None:
            # Use built-in default list
            default_path = Path(__file__).parent / "data" / "profanity.txt"
            if default_path.exists():
                word_list_path = default_path
            else:
                # Fallback to a minimal built-in list
                self.profanity_set = self._get_default_words()
                return

        word_list_path = Path(word_list_path)
        if not word_list_path.exists():
            raise FileNotFoundError(f"Profanity word list not found: {word_list_path}")

        with open(word_list_path, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip().lower()
                if word and not word.startswith("#"):  # Skip empty lines and comments
                    self.profanity_set.add(word)

        print(f"Loaded {len(self.profanity_set)} profanity words")

    def _get_default_words(self) -> set[str]:
        """Return a minimal default profanity word list."""
        # This is intentionally minimal - users should provide their own list
        # for comprehensive filtering
        return {
            "fuck", "fucking", "fucked", "fucker", "fuckin",
            "shit", "shitty", "bullshit",
            "ass", "asshole", "asses",
            "bitch", "bitches", "bitching",
            "damn", "damned", "goddamn",
            "hell",
            "crap",
            "dick", "dicks",
            "cock", "cocks",
            "pussy", "pussies",
            "cunt", "cunts",
            "whore", "whores",
            "slut", "sluts",
            "bastard", "bastards",
            "piss", "pissed", "pissing",
        }

    def _normalize_word(self, word: str) -> str:
        """Normalize a word for matching."""
        # Remove punctuation and convert to lowercase
        normalized = re.sub(r"[^\w]", "", word.lower())
        return normalized

    def detect(self, words: list[TranscribedWord]) -> list[ProfanityMatch]:
        """
        Detect profanity in a list of transcribed words.

        Args:
            words: List of TranscribedWord objects from transcription

        Returns:
            List of ProfanityMatch objects for detected profanities
        """
        matches = []

        for word in words:
            normalized = self._normalize_word(word.word)

            # Check exact match
            if normalized in self.profanity_set:
                matches.append(
                    ProfanityMatch(
                        word=normalized,
                        original_word=word.word,
                        start=word.start,
                        end=word.end,
                        confidence=word.confidence,
                    )
                )
                continue

            # Check if any profanity word is contained within this word
            # (handles cases like "motherfucker" containing "fuck")
            for profanity in self.profanity_set:
                if profanity in normalized and len(profanity) >= 4:
                    matches.append(
                        ProfanityMatch(
                            word=profanity,
                            original_word=word.word,
                            start=word.start,
                            end=word.end,
                            confidence=word.confidence,
                        )
                    )
                    break

        print(f"Detected {len(matches)} profanities")
        return matches

    def add_words(self, words: list[str]) -> None:
        """Add words to the profanity list."""
        for word in words:
            self.profanity_set.add(word.lower().strip())

    def remove_words(self, words: list[str]) -> None:
        """Remove words from the profanity list."""
        for word in words:
            self.profanity_set.discard(word.lower().strip())
