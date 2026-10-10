"""The object store factory and its secret handling (P0-I4-B)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_adapters.objectstore import DEV_SECRET, FsObjectStore, make_object_store, object_secret


def test_the_secret_comes_from_the_environment() -> None:
    assert object_secret({"TL_OBJECT_SECRET": "abc"}) == b"abc"
    assert object_secret({"TL_OBJECT_SECRET": "abc", "TL_ENV": "dev"}) == b"abc"


def test_the_dev_secret_needs_an_explicit_dev_environment() -> None:
    assert object_secret({"TL_ENV": "dev"}) == DEV_SECRET.encode()
    assert object_secret({"TL_ENV": "dev", "TL_OBJECT_SECRET": ""}) == DEV_SECRET.encode()


@pytest.mark.parametrize("env", [{}, {"TL_ENV": "prod"}, {"TL_ENV": ""}, {"TL_OBJECT_SECRET": ""}])
def test_without_a_secret_or_dev_it_fails_closed(env: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="TL_OBJECT_SECRET"):
        object_secret(env)


def test_the_fs_store_is_the_default_and_needs_a_secret(tmp_path: Path) -> None:
    store = make_object_store({"TL_OBJECT_ROOT": str(tmp_path), "TL_ENV": "dev"})
    assert isinstance(store, FsObjectStore) and store.root == tmp_path
    with pytest.raises(ValueError, match="TL_OBJECT_SECRET"):
        make_object_store({"TL_OBJECT_ROOT": str(tmp_path)})


def test_unknown_kinds_and_a_missing_bucket_are_refused() -> None:
    with pytest.raises(ValueError, match="'fs' or 's3'"):
        make_object_store({"TL_OBJECT_STORE": "gcs"})
    with pytest.raises(ValueError, match="TL_S3_BUCKET"):
        make_object_store({"TL_OBJECT_STORE": "s3"})
