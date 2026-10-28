"""ariseOS archive: a read-only, searchable mirror of the two private GitHub repos.

Section 13 of the automator's SERVER_HANDOFF.md (Rehchu/arise-youtube-automation).
Reference material for Claude sessions on the box: it never feeds the nightly job,
never writes to YouTube, never pushes to GitHub. This package imports nothing from
arise_server and never reads /etc/arise/secrets.
"""
VERSION = "1.0"
