#!/usr/bin/env python3

"""s&box public repository filtering helpers."""

import argparse
import json
import sys
from pathlib import PurePosixPath
from typing import Dict, Iterable, List, Optional, Set
import git_filter_repo as fr

class FilenameFilter:
    """Applies include/exclude rules and renames for git-filter-repo."""

    def __init__(self, config: Dict[str, object]) -> None:
        self._include_globs = tuple(_normalise_glob(p) for p in config.get("include_globs", []) or [])
        self._exclude_globs = tuple(_normalise_glob(p) for p in config.get("exclude_globs", []) or [])
        self._whitelisted_shaders = tuple(_normalise_glob(p) for p in config.get("whitelisted_shaders", []) or [])

        renames = config.get("path_renames", {}) or {}
        self._rename_targets: Dict[str, str] = {
            _normalise_path(src): str(dest)
            for src, dest in renames.items()
        }

        lfs_paths: Iterable[str] = config.get("lfs_paths", []) or []
        self._lfs_paths: Set[str] = { _normalise_path(path) for path in lfs_paths }

    def __call__(self, filename: bytes) -> Optional[bytes]:
        path_text = filename.decode("utf-8", "ignore")
        normalised = _normalise_path(path_text)
        path = PurePosixPath(normalised)

        if normalised in self._lfs_paths:
            return None

        allowed = _matches_any_glob(path, self._include_globs)

        if allowed and _matches_any_glob(path, self._exclude_globs):
            allowed = False

        if not allowed and _matches_any_glob(path, self._whitelisted_shaders):
            allowed = True

        if not allowed:
            return None

        rename_target = self._rename_targets.get(normalised)
        if rename_target:
            return rename_target.encode("utf-8")

        return filename


class BaselineCommitCallback:
    """Rewrites the root commit metadata for the public history."""

    _base_message = (
        "Open source release\n\n"
        "This commit imports the C# engine code and game files, excluding C++ source code."
    )

    def __call__(self, commit, metadata) -> None:  # pylint: disable=unused-argument
        if commit.parents:
            return

        commit.message = self._base_message.encode("utf-8")
        commit.message += b"\n\n[Source-Commit: " + commit.original_id + b"]\n"
        commit.author_name = b"s&box team"
        commit.author_email = b"sboxbot@facepunch.com"
        commit.committer_name = b"s&box team"
        commit.committer_email = b"sboxbot@facepunch.com"


def _normalise_path(value: str) -> str:
    return value.replace("\\", "/").lower()


def _normalise_glob(pattern: str) -> str:
    return _normalise_path(pattern or "")


def _matches_any_glob(path: PurePosixPath, patterns: Iterable[str]) -> bool:
    for glob in patterns:
        if path.full_match(glob):
            return True
    return False


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run git-filter-repo with s&box filters")
    parser.add_argument("--config", required=True, help="Path to JSON configuration file")
    args = parser.parse_args(argv)

    with open(args.config, "r", encoding="utf-8") as fp:
        config = json.load(fp)

    filename_filter = FilenameFilter(config)
    commit_callback = BaselineCommitCallback()

    options = fr.FilteringOptions.parse_args([], error_on_empty=False)
    options.force = True

    repo_filter = fr.RepoFilter(
        options,
        filename_callback=filename_filter,
        commit_callback=commit_callback,
    )

    repo_filter.run()
    return 0

if __name__ == "__main__":
    sys.exit(main())
