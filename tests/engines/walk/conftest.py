"""Fixtures for the walk engine's tests."""

import pytest

from tests.engines.walk.support import build_source_pdf, load_tool


@pytest.fixture(scope="session")
def render_pages_tool():
    return load_tool("render_pages")


@pytest.fixture(scope="session")
def dump_blocks_tool():
    return load_tool("dump_blocks")


@pytest.fixture
def work_dir(tmp_path):
    """A work directory holding an invented two-page source.pdf."""
    return build_source_pdf(tmp_path)
