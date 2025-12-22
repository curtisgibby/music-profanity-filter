"""
Music Profanity Filter

Automatically detect and remove profanity from music tracks using AI-powered
audio analysis and stem separation.
"""

__version__ = "0.1.0"

from .pipeline import MusicProfanityFilter

__all__ = ["MusicProfanityFilter"]
