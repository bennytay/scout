import pytest

from scout.urls import arxiv_id_from, canonicalize, doi_from, guess_type


@pytest.mark.parametrize("url,expected", [
    ("https://arxiv.org/abs/2510.01234v2", "https://arxiv.org/abs/2510.01234"),
    ("http://arxiv.org/pdf/2510.01234v1.pdf", "https://arxiv.org/abs/2510.01234"),
    ("https://www.arxiv.org/html/2510.01234v3", "https://arxiv.org/abs/2510.01234"),
    ("https://huggingface.co/papers/2510.01234", "https://arxiv.org/abs/2510.01234"),
    ("https://twitter.com/DrJimFan/status/123?s=20&t=abc", "https://x.com/DrJimFan/status/123"),
    ("https://mobile.x.com/DrJimFan/status/123", "https://x.com/DrJimFan/status/123"),
    ("https://github.com/HuggingFace/LeRobot/tree/main/src", "https://github.com/huggingface/lerobot"),
    ("https://github.com/huggingface/lerobot.git", "https://github.com/huggingface/lerobot"),
    ("https://github.com/org/repo/releases/tag/v1.2", "https://github.com/org/repo/releases/tag/v1.2"),
    ("https://youtu.be/abc123", "https://www.youtube.com/watch?v=abc123"),
    ("https://www.example.com/post/?utm_source=x&id=7&fbclid=zz", "https://example.com/post?id=7"),
    ("example.com/a/", "https://example.com/a"),
])
def test_canonicalize(url, expected):
    assert canonicalize(url) == expected


def test_canonicalize_is_idempotent():
    for u in ["https://arxiv.org/abs/2510.01234v2", "https://x.com/a/status/1", "https://example.com/x?b=2&a=1"]:
        assert canonicalize(canonicalize(u)) == canonicalize(u)


def test_ids():
    assert arxiv_id_from("see arXiv:2510.01234 for details") == "2510.01234"
    assert arxiv_id_from("version 2510.01234 of the app") is None  # no arxiv context → no false positive
    assert doi_from("https://doi.org/10.1109/LRA.2025.1234567.") == "10.1109/lra.2025.1234567"


def test_guess_type():
    assert guess_type("https://arxiv.org/abs/2510.01234") == "paper"
    assert guess_type("https://github.com/a/b") == "repo"
    assert guess_type("https://x.com/a/status/1") == "post"
    assert guess_type("https://huggingface.co/datasets/lerobot/aloha") == "dataset"
    assert guess_type("https://huggingface.co/lerobot/pi0") == "model"
    assert guess_type("https://spectrum.ieee.org/humanoid") == "article"
