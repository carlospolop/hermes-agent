"""Discord textual wake-prefix ingress contract."""

from types import SimpleNamespace

import discord
import pytest

from gateway.config import PlatformConfig
from plugins.platforms.discord.adapter import DiscordAdapter, _apply_yaml_config


def _adapter(*, prefix: str) -> DiscordAdapter:
    adapter = object.__new__(DiscordAdapter)
    adapter.config = PlatformConfig(enabled=True, token="test", extra={"wake_prefix": prefix})
    adapter._client = SimpleNamespace(user=SimpleNamespace(id=999, bot=True))
    adapter._dedup = SimpleNamespace(
        contains=lambda _message_id: False,
        is_duplicate=lambda _message_id: False,
    )
    adapter._allowed_role_ids = set()
    adapter._is_allowed_user = lambda *_args, **_kwargs: True
    adapter._get_allow_bots = lambda: "none"
    return adapter


def _message(content: str, *, guild=True):
    return SimpleNamespace(
        id=1,
        type=discord.MessageType.default,
        content=content,
        author=SimpleNamespace(id=42, bot=False),
        channel=SimpleNamespace(id=123),
        guild=SimpleNamespace(id=456) if guild else None,
        mentions=[],
    )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("hermes help", True),
        ("Hermes, investigate", True),
        ("HERMES", True),
        ("hello hermes", False),
        (" hermes help", False),
        ("hermesian question", False),
        ("", False),
    ],
)
def test_channel_ingress_requires_configured_leading_wake_token(content, expected):
    admitted, _ = _adapter(prefix="hermes")._discord_message_admission(
        _message(content), claim=False
    )
    assert admitted is expected


def test_textual_wake_prefix_does_not_change_dm_ingress():
    admitted, _ = _adapter(prefix="hermes")._discord_message_admission(
        _message("ordinary dm", guild=False), claim=False
    )
    assert admitted is True


def test_yaml_wake_prefix_is_seeded_into_adapter_extra(monkeypatch):
    monkeypatch.delenv("DISCORD_WAKE_PREFIX", raising=False)
    seeded = _apply_yaml_config({}, {"wake_prefix": "  hermes  "})
    assert seeded is not None
    assert seeded["wake_prefix"] == "hermes"
