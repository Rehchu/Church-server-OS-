"""Archive only authorized regular files, without following filesystem links."""
from __future__ import annotations

import os
import shutil
import stat

from . import files, sharing


def members(path: str, who=None, *, public: bool = False):
    base = os.path.realpath(path)

    def allowed(p):
        if os.path.islink(p):
            return False
        real = os.path.realpath(p)
        if real != base and not real.startswith(base + os.sep):
            return False
        # A public link must never include Pastors, even if its creator can.
        if public and sharing._under(real, os.path.realpath(sharing.pastors_path())):
            return False
        return not sharing.hidden(real, who)

    out = []
    if not allowed(base):
        return out
    for parent, dirs, names in os.walk(base, followlinks=False):
        dirs[:] = [d for d in dirs if d != '.Trash' and allowed(os.path.join(parent, d))]
        for name in names:
            full = os.path.join(parent, name)
            if not allowed(full):
                continue
            try:
                info = os.stat(full, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode):
                out.append((full, os.path.relpath(full, base), info.st_size))
    return out


def write_member(archive, base: str, relative: str, archive_name: str, who=None, *, public=False):
    """Open each component relative to held directory descriptors.

    Refuse symlink replacements between discovery and reading; check permission
    again at use. Caller must remove a partially written archive on failure.
    """
    parts = relative.split(os.sep)
    if any(p in ('', '.', '..') for p in parts) or os.path.isabs(relative):
        raise ValueError('invalid archive path')
    full = os.path.join(base, relative)
    if sharing.hidden(os.path.realpath(full), who) or (
        public and sharing._under(os.path.realpath(full), os.path.realpath(sharing.pastors_path()))
    ):
        raise PermissionError('archive permission changed')
    directory = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, 'rb') as src:
            if not stat.S_ISREG(os.fstat(src.fileno()).st_mode):
                raise ValueError('archive member is not a regular file')
            sharing.note_access(full, who, 'archive')
            with archive.open(archive_name, 'w') as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
    finally:
        os.close(directory)
