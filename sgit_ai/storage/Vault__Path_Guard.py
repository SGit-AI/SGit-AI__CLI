"""Vault__Path_Guard — contains attacker-influenced paths to a destination directory.

Vault tree-entry names and transfer-archive member names are chosen by whoever
authored the vault, not by the receiving user. Writing them with a bare
``os.path.join(dest, name)`` allows path traversal: an absolute path discards
``dest`` entirely, and ``../`` segments escape it. This guard rejects both and
verifies the resolved target stays under ``dest``, so a hostile name can never
overwrite files outside the working copy.

Lives in the storage layer (with its exception) so both storage and core can
use it without breaking the storage-must-not-import-core dependency rule.
"""
import os
import re
import unicodedata
from   osbot_utils.type_safe.Type_Safe   import Type_Safe

# Paths that must NEVER be written from vault data, at any depth — structural
# invariants, not preferences. git *refuses* .git (it does not merely ignore
# it); the same holds for the vault's own internals. A hostile or accidental
# vault head carrying these would, on checkout, drop attacker-controlled bytes
# into the victim's key/config directory or git-hook directory (code execution
# on the next git command). Distinct from ALWAYS_IGNORED_DIRS, which also holds
# preference-level entries (e.g. .github) that tracked-wins deliberately
# grandfathers — these never are.
VAULT_PROTECTED_DIRS     = {'.sg_vault', '.sg_vault_new', '.git'}
VAULT_PROTECTED_PREFIXES = ('.sg_vault_old_',)

# A case-insensitive or Unicode-normalising filesystem (macOS, Windows) resolves
# other spellings to the same directory: '.GIT', '.git.' / '.git ' (Windows drops
# trailing dots and spaces), 'GIT~1' / 'SG_VAU~1' (8.3 short names), '.git::$DATA'
# (an NTFS stream), and '.g\u200cit' (HFS+ ignores these code points). Git refuses
# all of them (CVE-2014-9390, CVE-2019-1353); so does this guard, on every platform,
# because the vault that carries the name may be checked out anywhere.
_IGNORABLE_CODEPOINTS = re.compile('[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u206a-\u206f\ufeff]')   # + U+200B,
_SHORT_NAME           = re.compile(r'^(git|sg_vau)~[0-9]+$|^sg[0-9a-f]{4}~[0-9]+$')        # U+2060, soft hyphen;
                                                                                         # hashed 8.3 (SG1A2B~1)

# `sgit vault uninit` leaves a full backup — store AND plaintext VAULT-KEY — next to
# the files as .vault__<...>.zip, and `sgit init --restore` restores the newest one
# it finds. Vault data must never plant one (a hostile vault could hand the victim
# its own key and history on the next restore), and a commit must never pick one up
# (it would push the old vault's key into the new vault).
_VAULT_BACKUP_ZIP     = re.compile(r'^\.vault__.*\.zip(\.sha256|\.manifest\.json)?$')
# 0.20.0 and earlier wrote the uninit backup as <vault-id>__<timestamp>__uninit.zip, a name
# nothing protected: a plain `sgit commit` after `init --restore` committed it, vault key and
# signing key included (review d3b8eef N1). Those names, and their sidecars, are protected too.
_LEGACY_BACKUP_ZIP    = re.compile(r'^[a-z0-9]{4,24}__\d{4}-\d\d-\d\dt\d\d-\d\d-\d\dz__[a-z0-9_-]+\.zip'
                                   r'(\.sha256|\.manifest\.json)?$')


class Vault__Unsafe_Path_Error(Exception):
    """Raised when a vault- or archive-supplied path would escape the working directory."""

    def __init__(self, message: str = 'refusing path that escapes the destination directory'):
        super().__init__(message)


class Vault__Unreadable_File_Error(Exception):
    """A working-copy file sgit cannot open (permission denied, a sharing violation, an
    I/O error). Never read as "deleted": a commit would remove it for everyone (review
    eed8084 B2). Commands that would record it refuse; status lists it as unreadable."""

    def __init__(self, rel_path: str, reason: str):
        self.rel_path = rel_path
        super().__init__(f'cannot read {rel_path} ({reason}); nothing was changed. sgit never records a file it '
                         f'cannot read as deleted: close the program holding it or fix its permissions, then run '
                         f'the command again (or add it to .gitignore)')


class Vault__Path_Guard(Type_Safe):
    WARNED = set()                                                # non-regular files already reported in this process


    def is_writable(self, base_dir: str, rel_path: str) -> bool:
        """True if vault data may write or delete rel_path under base_dir: it stays
        inside base_dir AND names no structural directory (.git, .sg_vault*).
        Every loop that writes or deletes vault-supplied paths skips what fails this."""
        return not self.is_protected(rel_path) and self.is_safe(base_dir, rel_path)

    def is_safe(self, base_dir: str, rel_path: str) -> bool:
        """True if rel_path stays within base_dir; never raises."""
        try:
            self.safe_join(base_dir, rel_path)
            return True
        except Vault__Unsafe_Path_Error:
            return False

    def is_protected(self, rel_path: str) -> bool:
        """True if any segment of rel_path names a structural directory that
        must never be written from vault data (.git, .sg_vault, .sg_vault_new,
        .sg_vault_old_*). Checked against BOTH separators so a Windows-style
        path is caught on POSIX too."""
        raw = '' if rel_path is None else str(rel_path)
        for segment in raw.replace('\\', '/').split('/'):
            canonical = self.canonical_segment(segment)
            for name in {segment, canonical, canonical.upper().lower()}:     # '.gıt' (dotless i) is '.GIT' on NTFS
                if name in VAULT_PROTECTED_DIRS:
                    return True
                if any(name.startswith(prefix) for prefix in VAULT_PROTECTED_PREFIXES):
                    return True
                if _SHORT_NAME.match(name) or _VAULT_BACKUP_ZIP.match(name) or _LEGACY_BACKUP_ZIP.match(name):
                    return True
        return False

    def canonical_segment(self, segment: str) -> str:
        """The name a case-insensitive, normalising filesystem would resolve
        segment to: ignorable code points removed, NFC, case-folded, any NTFS
        stream suffix (':...') cut, trailing dots and spaces stripped."""
        name = _IGNORABLE_CODEPOINTS.sub('', str(segment or ''))
        name = unicodedata.normalize('NFC', name).casefold()
        name = name.split(':', 1)[0]
        return name.rstrip('. ')

    def safe_join(self, base_dir: str, rel_path: str) -> str:
        """Join rel_path onto base_dir, or raise Vault__Unsafe_Path_Error.

        Rejects: empty paths, absolute paths (POSIX or Windows), any '..'
        component (checked against BOTH separators, so a Windows-style
        '..\\..\\x' is caught on POSIX too), and any path whose resolved
        location is not inside base_dir. Returns the absolute, contained path.

        The join uses the ORIGINAL rel_path, never a separator-normalised copy:
        on POSIX a backslash is a legal filename character, so rewriting '\\'
        to '/' would silently turn the file 'weird\\name.txt' into the
        directory 'weird/name.txt'. Normalisation is used only for detection.
        """
        if self.is_protected(rel_path):
            raise Vault__Unsafe_Path_Error(f'refusing a structural path from vault data (.git / .sg_vault): {rel_path!r}')
        raw = '' if rel_path is None else str(rel_path)
        if not raw.strip():
            raise Vault__Unsafe_Path_Error(f'refusing empty path: {rel_path!r}')
        if raw.startswith('/') or raw.startswith('\\') or os.path.isabs(raw):
            raise Vault__Unsafe_Path_Error(f'refusing absolute path: {rel_path!r}')

        # Detection only — split on both separators so traversal is caught on any platform.
        if any(part == '..' for part in raw.replace('\\', '/').split('/')):
            raise Vault__Unsafe_Path_Error(f'refusing parent-directory traversal: {rel_path!r}')

        base_abs = os.path.abspath(base_dir)
        full     = os.path.abspath(os.path.join(base_abs, raw))   # original path, not normalised
        if full != base_abs and not full.startswith(base_abs + os.sep):
            raise Vault__Unsafe_Path_Error(
                f'refusing path escaping destination {base_dir!r}: {rel_path!r}')
        if self.has_link_component(base_abs, full):              # sgit never writes through a link inside the tree
            raise Vault__Unsafe_Path_Error(
                f'refusing to write through a symlink inside {base_dir!r}: {rel_path!r}')
        if not self.is_inside(base_abs, os.path.realpath(full)):   # belt and braces: the resolved path stays inside
            raise Vault__Unsafe_Path_Error(
                f'refusing path that resolves outside {base_dir!r} through a symlink: {rel_path!r}')
        return full

    def has_link_component(self, base_abs: str, full: str) -> bool:
        """True if full, or any folder between base_abs and it, is a symlink. Links
        ABOVE base_abs (a symlinked home, /tmp -> /private/tmp) are not checked."""
        rel = os.path.relpath(full, base_abs)
        if rel in ('.', ''):
            return False
        path = base_abs
        for part in rel.split(os.sep):
            path = os.path.join(path, part)
            if os.path.islink(path):
                return True
        return False

    def is_inside(self, base_dir: str, real_path: str) -> bool:
        """True if real_path (already resolved) lies in base_dir once base_dir's
        own symlinks are resolved too (/tmp -> /private/tmp on macOS)."""
        base_real = os.path.realpath(base_dir)
        return real_path == base_real or real_path.startswith(base_real.rstrip(os.sep) + os.sep)

    def is_link(self, full_path: str) -> bool:
        """sgit does not store symlinks and never follows one inside the working copy
        (trees have no link type, so a followed link was committed as a copy of its
        target: a link to ~/.ssh/id_rsa, or to .sg_vault/local/vault_key, put that
        secret in the vault). Every working-copy scan skips these. Windows junctions
        count as links too (review L4)."""
        if os.path.islink(full_path):
            return True
        is_junction = getattr(os.path, 'isjunction', None)        # Python 3.12+
        return bool(is_junction and is_junction(full_path))

    def read_regular(self, full_path: str, rel_path: str = None):
        """The bytes of a regular file, or None when there is no file to record: a link
        (ELOOP), a file gone since the listing, or a FIFO, socket or device (skipped with
        a warning). Opened with O_NOFOLLOW (a link swapped in after the check is not
        followed) and O_NONBLOCK (a FIFO never blocks), then fstat'ed on the open
        descriptor, so the check and the read are about the same file (review L4).
        Any other failure (permission denied, a file another program holds open, EIO)
        raises Vault__Unreadable_File_Error: returning None made status report the file
        deleted and commit remove it for everyone (review eed8084 B2)."""
        import errno
        import stat as _stat
        rel_path = rel_path or full_path
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
        try:
            fd = os.open(full_path, flags)
        except FileNotFoundError:
            return None                                           # gone since the listing: it is deleted
        except OSError as error:
            if error.errno == errno.ELOOP or self.is_link(full_path):
                return None                                       # a link: never followed, never stored
            raise Vault__Unreadable_File_Error(rel_path, error.strerror or type(error).__name__)
        try:
            if not _stat.S_ISREG(os.fstat(fd).st_mode):
                self.warn_not_regular(rel_path)
                return None
            with os.fdopen(fd, 'rb') as f:
                fd = None
                return f.read()
        except OSError as error:
            raise Vault__Unreadable_File_Error(rel_path, error.strerror or type(error).__name__)
        finally:
            if fd is not None:
                os.close(fd)

    def warn_not_regular(self, rel_path: str) -> None:
        if rel_path in Vault__Path_Guard.WARNED:
            return
        Vault__Path_Guard.WARNED.add(rel_path)
        import sys
        print(f'  warning: skipped {rel_path}: not a regular file (a FIFO, socket or device); sgit stores files only',
              file=sys.stderr)
