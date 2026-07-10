from __future__ import annotations

import base64

from src.infra.artifact_store import ArtifactStore
from src.infra.image_artifacts import IMAGE_ARTIFACT_URL_PREFIX, save_image_artifact


class _FakeContext:
    def __init__(self, store: ArtifactStore) -> None:
        self._store = store

    def create_artifact(self, run_id, name, content, mime_type):  # noqa: ANN001
        return self._store.create(run_id, name, content, mime_type)


def test_read_bytes_roundtrip(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    data = b"\x89PNG\r\n\x1a\nfake-bytes"
    store.create("run1", "photo.png", data, "image/png")

    result = store.read_bytes("run1", "photo.png")

    assert result is not None
    read_data, mime_type = result
    assert read_data == data
    assert mime_type == "image/png"


def test_read_bytes_missing_returns_none(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    assert store.read_bytes("run1", "does-not-exist.png") is None


def test_save_image_artifact_builds_url(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    ctx = _FakeContext(store)
    b64 = base64.b64encode(b"fake-image-data").decode()

    url = save_image_artifact(ctx, "run1", b64, "image/png")

    assert url is not None
    assert url.startswith(f"{IMAGE_ARTIFACT_URL_PREFIX}/run1/")
    assert url.endswith(".png")

    # артефакт реально сохранился и читается обратно
    name = url.rsplit("/", 1)[-1]
    read_data, mime_type = store.read_bytes("run1", name)
    assert read_data == b"fake-image-data"
    assert mime_type == "image/png"


def test_save_image_artifact_picks_extension_from_mime(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    ctx = _FakeContext(store)
    b64 = base64.b64encode(b"jpeg-bytes").decode()

    url = save_image_artifact(ctx, "run1", b64, "image/jpeg")

    assert url.endswith(".jpeg")


def test_save_image_artifact_none_context_returns_none() -> None:
    b64 = base64.b64encode(b"data").decode()
    assert save_image_artifact(None, "run1", b64, "image/png") is None


def test_save_image_artifact_empty_run_id_returns_none(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    ctx = _FakeContext(store)
    b64 = base64.b64encode(b"data").decode()
    assert save_image_artifact(ctx, "", b64, "image/png") is None


def test_save_image_artifact_invalid_base64_returns_none(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    ctx = _FakeContext(store)
    assert save_image_artifact(ctx, "run1", "", "image/png") is None


def test_save_image_artifact_ctx_exception_returns_none() -> None:
    class _BrokenContext:
        def create_artifact(self, *args, **kwargs):  # noqa: ANN001
            raise RuntimeError("disk full")

    b64 = base64.b64encode(b"data").decode()
    assert save_image_artifact(_BrokenContext(), "run1", b64, "image/png") is None
