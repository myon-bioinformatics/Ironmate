"""Safe ``-o`` file output shared by the grid CLIs (stdlib only, no import-time I/O).

Default: exclusive create, so an existing file or symlink (even a dangling one) is never truncated.
``force=True``: write a temporary file in the same directory and ``os.replace`` it onto the path,
which replaces a symlink itself instead of writing through it to its target.
"""
from __future__ import annotations
import os, tempfile

__all__ = ['write_output']


def write_output(path, data, force=False):
    """Write bytes to ``path``; raise FileExistsError (an OSError) unless ``force``."""
    if not force:
        try:
            with open(path, 'xb') as handle:
                handle.write(data)
        except FileExistsError:
            raise FileExistsError(f'refusing to overwrite existing {path} (use --force)') from None
        return
    if os.path.isdir(path):
        raise IsADirectoryError(f'{path} is a directory')
    fd, tmp = tempfile.mkstemp(prefix='.tmp-', dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
