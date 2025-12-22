"""
Lyrics fetching module.

Fetches lyrics from Genius using the lyricsgenius library.
"""

import os
import re
from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError

try:
    import lyricsgenius
    GENIUS_AVAILABLE = True
except ImportError:
    GENIUS_AVAILABLE = False


class LyricsFetcher:
    """Fetches song lyrics from Genius."""

    def __init__(self, access_token: str | None = None):
        """
        Initialize the lyrics fetcher.

        Args:
            access_token: Genius API access token. If not provided,
                         looks for GENIUS_ACCESS_TOKEN environment variable.
        """
        if not GENIUS_AVAILABLE:
            raise ImportError(
                "lyricsgenius is required for lyrics fetching. "
                "Install it with: pip install lyricsgenius"
            )

        self.access_token = access_token or os.environ.get("GENIUS_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError(
                "Genius access token required. Set GENIUS_ACCESS_TOKEN environment "
                "variable or pass access_token parameter."
            )

        self._genius = None

    @property
    def genius(self):
        """Lazy-load the Genius client."""
        if self._genius is None:
            self._genius = lyricsgenius.Genius(
                self.access_token,
                verbose=False,
                remove_section_headers=False,  # Keep [Verse], [Chorus] etc.
                skip_non_songs=True,
            )
        return self._genius

    def fetch(self, title: str, artist: str) -> str | None:
        """
        Fetch lyrics for a song.

        Args:
            title: Song title
            artist: Artist name

        Returns:
            Lyrics text, or None if not found
        """
        print(f"Searching Genius for '{title}' by {artist}...")

        try:
            song = self.genius.search_song(title, artist)
            if song:
                print(f"Found: {song.full_title}")
                return self._clean_lyrics(song.lyrics)
            else:
                print("No lyrics found on Genius")
                return None
        except Exception as e:
            print(f"Error fetching lyrics: {e}")
            return None

    def fetch_from_file(self, audio_path: Path) -> str | None:
        """
        Fetch lyrics using metadata from an audio file.

        Args:
            audio_path: Path to the audio file

        Returns:
            Lyrics text, or None if not found
        """
        audio_path = Path(audio_path)

        # Try to get artist and title from ID3 tags
        title, artist = self._get_metadata(audio_path)

        if not title or not artist:
            # Fall back to parsing filename
            title, artist = self._parse_filename(audio_path)

        if not title or not artist:
            print("Could not determine song title/artist from file")
            return None

        return self.fetch(title, artist)

    def _get_metadata(self, audio_path: Path) -> tuple[str | None, str | None]:
        """Extract title and artist from ID3 tags."""
        try:
            tags = ID3(str(audio_path))
            title = str(tags.get("TIT2", "")) or None
            artist = str(tags.get("TPE1", "")) or None
            return title, artist
        except ID3NoHeaderError:
            return None, None

    def _parse_filename(self, audio_path: Path) -> tuple[str | None, str | None]:
        """
        Parse title and artist from filename.

        Supports formats like:
        - "Artist - Title.mp3"
        - "01 - Title - Artist.mp3"
        - "01. Title - Artist.mp3"
        """
        stem = audio_path.stem

        # Remove track numbers like "01 - ", "01. ", "04 - "
        stem = re.sub(r"^\d+[\s\-\.]+", "", stem)

        # Try "Artist - Title" or "Title - Artist" format
        if " - " in stem:
            parts = stem.split(" - ", 1)
            if len(parts) == 2:
                # Heuristic: if first part looks like a title (longer), swap
                # Otherwise assume "Artist - Title"
                return parts[1].strip(), parts[0].strip()

        return None, None

    def _clean_lyrics(self, lyrics: str) -> str:
        """Clean up lyrics from Genius."""
        if not lyrics:
            return lyrics

        # Remove the song title/contributor line that Genius adds at the start
        # e.g., "Father Figure Lyrics[Verse 1]..." -> "[Verse 1]..."
        lines = lyrics.split("\n")
        if lines and "Lyrics" in lines[0]:
            lines = lines[1:]

        # Remove empty lines at start/end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        # Remove "XXXEmbed" at the end (Genius artifact)
        if lines:
            lines[-1] = re.sub(r"\d*Embed$", "", lines[-1])

        # Remove "You might also like" artifacts
        cleaned = []
        skip_next = 0
        for line in lines:
            if skip_next > 0:
                skip_next -= 1
                continue
            if line.strip() == "You might also like":
                skip_next = 3  # Skip this + next 3 lines (usually song suggestions)
                continue
            cleaned.append(line)

        return "\n".join(cleaned)
