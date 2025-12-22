# Music Profanity Filter

Automatically detect and remove profanity from music tracks using AI-powered audio analysis and stem separation.

## Why?

Sometimes you want to enjoy music without explicit language—whether for kids, work environments, or personal preference. Commercial "clean" versions aren't always available, and manually editing audio is tedious and requires expertise.

This tool automates the entire process: it listens to a song, identifies profane words, and creates a clean version where those words are muted while the instrumental continues playing naturally.

## What?

The tool performs these steps:

1. **Stem Separation** — Uses [Demucs](https://github.com/facebookresearch/demucs) to split the track into vocals and instrumentals
2. **Transcription** — Uses [OpenAI Whisper](https://github.com/openai/whisper) to transcribe vocals with word-level timestamps
3. **Lyrics Alignment** — Optionally aligns transcription against reference lyrics for improved accuracy
4. **Profanity Detection** — Matches words against a configurable profanity list
5. **Audio Editing** — Mutes profane words in the vocal track
6. **Recombination** — Merges edited vocals with instrumentals
7. **Metadata Preservation** — Copies ID3 tags (artist, album, cover art) and embeds synchronized lyrics

The result: a clean version of the song where profanity is silenced but the instrumental plays through, sounding natural rather than having jarring gaps or bleeps.

## How?

### Installation

```bash
# Clone the repository
git clone https://github.com/curtisgibby/music-profanity-filter.git
cd music-profanity-filter

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the package
pip install -e .
```

**Requirements:**
- Python 3.10+
- FFmpeg (install via `brew install ffmpeg` on macOS)

### Usage

```bash
# Basic usage — creates "song (clean).mp3"
music-clean song.mp3

# Auto-fetch lyrics from Genius (recommended!)
music-clean song.mp3 --fetch-lyrics

# Or provide lyrics manually
music-clean song.mp3 --lyrics lyrics.txt

# Preview detected profanities before processing
music-clean song.mp3 --fetch-lyrics --preview

# Overwrite original file instead of creating (clean) copy
music-clean song.mp3 --overwrite

# Process multiple files (each fetches its own lyrics)
music-clean *.mp3 --fetch-lyrics

# Output to specific directory
music-clean song.mp3 -o ./clean/

# Use a larger Whisper model for better accuracy (slower)
music-clean song.mp3 -m medium
```

### Options

| Flag | Description |
|------|-------------|
| `--fetch-lyrics`, `-f` | Auto-fetch lyrics from Genius (requires API token) |
| `--genius-token` | Genius API token (or set `GENIUS_ACCESS_TOKEN` env var) |
| `--lyrics FILE` | Reference lyrics file for improved alignment accuracy |
| `--preview`, `-p` | Preview detected profanities and confirm before processing |
| `--overwrite`, `-w` | Replace original file instead of creating "(clean)" copy |
| `--output-dir`, `-o` | Output directory for cleaned files |
| `--profanity-list`, `-l` | Custom profanity word list (one word per line) |
| `--whisper-model`, `-m` | Whisper model size: tiny, base, small, medium, large |
| `--demucs-model` | Demucs model: htdemucs, htdemucs_ft, mdx_extra |
| `--detect-only`, `-d` | Only detect profanities, don't create cleaned file |
| `--keep-temp` | Keep intermediate files (stems, edited vocals) |

### Automatic Lyrics Fetching (Genius)

The easiest way to use this tool is with `--fetch-lyrics`, which automatically fetches lyrics from [Genius](https://genius.com).

**Setup:**

1. Create a free account at [genius.com/api-clients](https://genius.com/api-clients)
2. Create a new API client and copy your access token
3. Set the token as an environment variable:

```bash
export GENIUS_ACCESS_TOKEN=your_token_here
```

Or create a `.env` file in your project directory:

```
GENIUS_ACCESS_TOKEN=your_token_here
```

**How it works:**

1. Reads artist and title from the MP3's ID3 tags
2. Falls back to parsing the filename if no tags (e.g., "Artist - Title.mp3")
3. Searches Genius and fetches the lyrics
4. Cleans up Genius artifacts (embed links, song suggestions, etc.)

### Lyrics File Format

Plain text, one line per line of the song. Section headers like `[Verse 1]` are automatically ignored:

```
[Verse 1]
When I found you, you were young, wayward, lost in the cold
Pulled up to you in the Jag', turned your rags into gold
...

[Chorus]
I'll be your father figure, I drink that brown liquor
...
```

**Why provide lyrics?** Whisper sometimes mishears words, especially in songs with heavy production. Providing reference lyrics lets the tool align timestamps to the correct words, ensuring profanity is detected even when Whisper's transcription is imperfect.

### Custom Profanity List

Create a text file with one word per line:

```
# my-words.txt
fuck
shit
# Lines starting with # are comments
```

Then use it:

```bash
music-clean song.mp3 --profanity-list my-words.txt
```

## How It Works

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              INPUT                                      │
│                    song.mp3 + (optional) lyrics.txt                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         STEM SEPARATION                                 │
│                            (Demucs)                                     │
│                    vocals.wav + instrumentals.wav                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         TRANSCRIPTION                                   │
│                           (Whisper)                                     │
│              Word-level timestamps from vocal track                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LYRICS ALIGNMENT                                   │
│                   (if reference lyrics provided)                        │
│         Align transcription to correct lyrics via difflib               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     PROFANITY DETECTION                                 │
│              Match words against profanity word list                    │
│                [(start, end, word), ...]                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       AUDIO EDITING                                     │
│                          (pydub)                                        │
│              Mute vocal track at profanity timestamps                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    RECOMBINE + METADATA                                 │
│         Mix edited vocals + instrumentals → cleaned MP3                 │
│      Copy ID3 tags + embed synchronized lyrics (SYLT frame)             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              OUTPUT                                     │
│                      song (clean).mp3                                   │
│           With all original metadata + synced lyrics                    │
└─────────────────────────────────────────────────────────────────────────┘
```

## Performance Notes

- **First run is slow** — Whisper and Demucs models are downloaded (~1-2GB)
- **Subsequent runs** — ~2-3 minutes per song on Apple Silicon
- **Whisper model size** — `base` is fast with decent accuracy; `medium` or `large` are more accurate but slower
- **Lyrics alignment** — Highly recommended for accurate detection; without it, Whisper may mishear words

## Dependencies

- [Demucs](https://github.com/facebookresearch/demucs) — AI-powered music source separation
- [OpenAI Whisper](https://github.com/openai/whisper) — Speech recognition with word timestamps
- [lyricsgenius](https://github.com/johnwmillr/LyricsGenius) — Genius lyrics fetching
- [pydub](https://github.com/jiaaro/pydub) — Audio manipulation
- [mutagen](https://github.com/quodlibet/mutagen) — ID3 tag handling
- [click](https://click.palletsprojects.com/) — CLI framework

## License

MIT
