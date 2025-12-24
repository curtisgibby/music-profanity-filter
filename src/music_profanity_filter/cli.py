"""
Command-line interface for the music profanity filter.
"""

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from .pipeline import MusicProfanityFilter

# Load .env file if present
load_dotenv()


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS.ms"""
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:05.2f}"


def print_profanities(profanities) -> None:
    """Pretty print detected profanities."""
    click.echo("\nDetected profanities:")
    click.echo("-" * 50)
    for i, p in enumerate(profanities, 1):
        time_str = f"{format_time(p.start)} - {format_time(p.end)}"
        click.echo(f"  {i:3}. [{time_str}] {p.original_word!r}")
    click.echo("-" * 50)
    click.echo(f"Total: {len(profanities)} profanities found\n")


@click.command()
@click.argument("input_files", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output-dir", "-o",
    type=click.Path(file_okay=False, path_type=Path),
    help="Output directory for cleaned files. Defaults to same directory as input.",
)
@click.option(
    "--overwrite", "-w",
    is_flag=True,
    help="Overwrite original files instead of creating '(clean)' copies.",
)
@click.option(
    "--preview", "-p",
    is_flag=True,
    help="Preview detected profanities before processing and confirm.",
)
@click.option(
    "--profanity-list", "-l",
    type=click.Path(exists=True, path_type=Path),
    help="Path to custom profanity word list (one word per line).",
)
@click.option(
    "--whisper-model", "-m",
    type=click.Choice(["tiny", "base", "small", "medium", "large"]),
    default="base",
    help="Whisper model size. Larger = more accurate but slower.",
)
@click.option(
    "--demucs-model",
    type=click.Choice(["htdemucs", "htdemucs_ft", "mdx_extra"]),
    default="htdemucs",
    help="Demucs model for stem separation.",
)
@click.option(
    "--keep-temp",
    is_flag=True,
    help="Keep temporary files (stems, edited vocals) for debugging.",
)
@click.option(
    "--detect-only", "-d",
    is_flag=True,
    help="Only detect profanities, don't create cleaned files.",
)
@click.option(
    "--generate-edl", "-e",
    is_flag=True,
    help="Generate EDL file for manual timestamp review. Saves stems for re-use.",
)
@click.option(
    "--apply-edl",
    is_flag=False,
    flag_value="__AUTO__",
    default=None,
    help="Apply edits from an EDL file. Defaults to {title}.edl.json if no path specified.",
)
@click.option(
    "--lyrics",
    type=click.Path(exists=True, path_type=Path),
    help="Path to lyrics file for improved alignment accuracy.",
)
@click.option(
    "--fetch-lyrics", "-f",
    is_flag=True,
    help="Automatically fetch lyrics from Genius (requires GENIUS_ACCESS_TOKEN).",
)
@click.option(
    "--genius-token",
    envvar="GENIUS_ACCESS_TOKEN",
    help="Genius API access token (or set GENIUS_ACCESS_TOKEN env var).",
)
def main(
    input_files: tuple[Path],
    output_dir: Path | None,
    overwrite: bool,
    preview: bool,
    profanity_list: Path | None,
    whisper_model: str,
    demucs_model: str,
    keep_temp: bool,
    detect_only: bool,
    generate_edl: bool,
    apply_edl: str | None,
    lyrics: Path | None,
    fetch_lyrics: bool,
    genius_token: str | None,
):
    """
    Clean profanity from music tracks.

    Automatically detects and mutes profane words in songs, leaving the
    instrumental playing through for a natural sound.

    Examples:

        music-clean song.mp3

        music-clean *.mp3 --preview

        music-clean song.mp3 --overwrite

        music-clean album/*.mp3 -o ./clean/

    EDL Workflow (for manual timestamp correction):

        music-clean song.mp3 --fetch-lyrics --generate-edl

        # Edit the .edl.json file to correct timestamps

        music-clean song.mp3 --apply-edl  # Uses song.edl.json by default
    """
    if not input_files:
        click.echo("No input files specified. Use --help for usage information.")
        sys.exit(1)

    # Initialize the filter
    click.echo("Initializing music profanity filter...")
    filter_instance = MusicProfanityFilter(
        demucs_model=demucs_model,
        whisper_model=whisper_model,
        profanity_list_path=profanity_list,
        keep_temp_files=keep_temp,
    )

    # Initialize lyrics fetcher if needed
    lyrics_fetcher = None
    if fetch_lyrics:
        try:
            from .lyrics import LyricsFetcher
            lyrics_fetcher = LyricsFetcher(access_token=genius_token)
            click.echo("Genius lyrics fetching enabled")
        except (ImportError, ValueError) as e:
            click.secho(f"Warning: {e}", fg="yellow")
            click.echo("Continuing without automatic lyrics fetching...")

    # Load lyrics from file if provided (applies to all files)
    shared_lyrics_text = None
    if lyrics:
        shared_lyrics_text = lyrics.read_text(encoding="utf-8")
        click.echo(f"Loaded lyrics from {lyrics}")

    # Process each file
    results = []
    for input_path in input_files:
        click.echo(f"\n{'=' * 60}")
        click.echo(f"Processing: {input_path}")
        click.echo("=" * 60)

        # Determine lyrics for this file
        lyrics_text = shared_lyrics_text
        if not lyrics_text and lyrics_fetcher:
            # Try to fetch lyrics from Genius
            fetched = lyrics_fetcher.fetch_from_file(input_path)
            if fetched:
                lyrics_text = fetched

        # Determine output path
        if output_dir:
            output_path = output_dir / f"{input_path.stem} (clean){input_path.suffix}"
        else:
            output_path = None  # Let pipeline determine

        if detect_only:
            # Just detect and report
            profanities = filter_instance.detect_only(input_path)
            if profanities:
                print_profanities(profanities)
            else:
                click.echo("\nNo profanity detected!")
            continue

        if apply_edl:
            # Resolve EDL path (use default if "__AUTO__")
            if apply_edl == "__AUTO__":
                edl_path = input_path.parent / f"{input_path.stem}.edl.json"
            else:
                edl_path = Path(apply_edl)

            if not edl_path.exists():
                click.secho(f"Error: EDL file not found: {edl_path}", fg="red")
                continue

            # Apply edits from EDL file
            result = filter_instance.apply_edl(
                input_path=input_path,
                edl_path=edl_path,
                output_path=output_path,
                overwrite=overwrite,
            )
            results.append(result)

            if not result.success:
                click.secho(f"Error: {result.error}", fg="red")
            elif result.profanities_found:
                click.secho(
                    f"Applied {len(result.profanities_found)} edits -> {result.output_path}",
                    fg="green",
                )
            else:
                click.secho("No edits in EDL file.", fg="yellow")
            continue

        if generate_edl:
            # Generate EDL file for manual review
            result = filter_instance.generate_edl(
                input_path=input_path,
                lyrics=lyrics_text,
            )
            results.append(result)

            if not result.success:
                click.secho(f"Error: {result.error}", fg="red")
            elif result.profanities_found:
                print_profanities(result.profanities_found)
                click.secho(f"EDL saved to: {result.edl_path}", fg="green")
                click.secho(f"Stems saved to: {result.stems_dir}", fg="green")
            else:
                click.secho("No profanity found, no EDL generated.", fg="yellow")
            continue

        # Define preview callback
        def preview_callback(profanities):
            print_profanities(profanities)
            if preview:
                return click.confirm("Proceed with cleaning?", default=True)
            return True

        # Run the filter
        result = filter_instance.filter(
            input_path=input_path,
            output_path=output_path,
            overwrite=overwrite,
            preview_callback=preview_callback,
            lyrics=lyrics_text,
        )
        results.append(result)

        if not result.success:
            click.secho(f"Error: {result.error}", fg="red")
        elif result.profanities_found:
            click.secho(
                f"Cleaned {len(result.profanities_found)} profanities -> {result.output_path}",
                fg="green",
            )
        else:
            click.secho("No profanity found, file unchanged.", fg="yellow")

    # Summary
    if len(input_files) > 1 and not detect_only:
        click.echo(f"\n{'=' * 60}")
        click.echo("Summary")
        click.echo("=" * 60)
        successful = sum(1 for r in results if r.success)
        total_profanities = sum(len(r.profanities_found) for r in results)
        click.echo(f"Files processed: {successful}/{len(results)}")
        if generate_edl:
            click.echo(f"Total profanities detected: {total_profanities}")
        else:
            click.echo(f"Total profanities cleaned: {total_profanities}")


if __name__ == "__main__":
    main()
