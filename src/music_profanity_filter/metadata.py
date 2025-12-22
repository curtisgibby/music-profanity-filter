"""
Metadata handling module.

Copies ID3 tags from source to destination and embeds synchronized lyrics.
"""

import shutil
from pathlib import Path

from mutagen.id3 import ID3, SYLT, Encoding, ID3NoHeaderError
from mutagen.mp3 import MP3


def copy_tags(source_path: Path, dest_path: Path) -> None:
    """
    Copy all ID3 tags from source file to destination file.

    Args:
        source_path: Path to the original audio file
        dest_path: Path to the file to copy tags to
    """
    source_path = Path(source_path)
    dest_path = Path(dest_path)

    try:
        # Load source tags
        source_tags = ID3(str(source_path))
    except ID3NoHeaderError:
        print("No ID3 tags found in source file")
        return

    try:
        # Try to load existing tags on dest, or create new
        dest_tags = ID3(str(dest_path))
    except ID3NoHeaderError:
        # No tags exist, create new ID3 header
        dest_audio = MP3(str(dest_path))
        dest_audio.add_tags()
        dest_audio.save()
        dest_tags = ID3(str(dest_path))

    # Copy all frames from source to dest
    for frame_id in source_tags.keys():
        dest_tags[frame_id] = source_tags[frame_id]

    dest_tags.save(str(dest_path))
    print(f"Copied ID3 tags from original file")


def embed_synced_lyrics(
    audio_path: Path,
    words: list,  # list of TranscribedWord
    language: str = "eng",
) -> None:
    """
    Embed synchronized lyrics into an MP3 file using the SYLT frame.

    Args:
        audio_path: Path to the MP3 file
        words: List of TranscribedWord objects with timing info
        language: ISO 639-2 language code (default: "eng" for English)
    """
    audio_path = Path(audio_path)

    if not audio_path.suffix.lower() == ".mp3":
        print(f"Synced lyrics only supported for MP3 files, skipping for {audio_path.suffix}")
        return

    try:
        tags = ID3(str(audio_path))
    except ID3NoHeaderError:
        audio = MP3(str(audio_path))
        audio.add_tags()
        audio.save()
        tags = ID3(str(audio_path))

    # Build SYLT data: list of (text, timestamp_ms) tuples
    # SYLT format expects timestamps in milliseconds
    sylt_data = []
    for word in words:
        timestamp_ms = int(word.start * 1000)
        # Add the word with its timestamp
        sylt_data.append((word.word + " ", timestamp_ms))

    # Remove any existing SYLT frames
    tags.delall("SYLT")

    # Create SYLT frame
    # type=1 means "lyrics" (as opposed to other text types)
    sylt_frame = SYLT(
        encoding=Encoding.UTF8,
        lang=language,
        format=2,  # milliseconds
        type=1,  # lyrics
        desc="Synchronized lyrics",
        text=sylt_data,
    )

    tags.add(sylt_frame)
    tags.save(str(audio_path))
    print(f"Embedded synchronized lyrics ({len(words)} words)")


def generate_lrc(words: list, output_path: Path | None = None) -> str:
    """
    Generate LRC format lyrics from transcribed words.

    Args:
        words: List of TranscribedWord objects
        output_path: Optional path to save .lrc file

    Returns:
        LRC formatted string
    """
    lines = []
    current_line = []
    current_line_start = None

    for word in words:
        if current_line_start is None:
            current_line_start = word.start

        current_line.append(word.word)

        # Start new line on punctuation or every ~10 words
        if (
            word.word.rstrip().endswith((".", "!", "?", ","))
            or len(current_line) >= 10
        ):
            # Format timestamp as [mm:ss.xx]
            minutes = int(current_line_start // 60)
            seconds = current_line_start % 60
            timestamp = f"[{minutes:02d}:{seconds:05.2f}]"

            line_text = " ".join(w.strip() for w in current_line)
            lines.append(f"{timestamp}{line_text}")

            current_line = []
            current_line_start = None

    # Don't forget remaining words
    if current_line and current_line_start is not None:
        minutes = int(current_line_start // 60)
        seconds = current_line_start % 60
        timestamp = f"[{minutes:02d}:{seconds:05.2f}]"
        line_text = " ".join(w.strip() for w in current_line)
        lines.append(f"{timestamp}{line_text}")

    lrc_content = "\n".join(lines)

    if output_path:
        output_path = Path(output_path)
        output_path.write_text(lrc_content, encoding="utf-8")
        print(f"Saved LRC lyrics to {output_path}")

    return lrc_content
