from __future__ import annotations

import os
from pathlib import Path

import pytest

from dealbot.settings import AppSettings, ConfigurationError, load_project_env, render_bootstrap_diagnostics


def test_load_project_env_uses_project_root_dotenv_without_overwriting_existing_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / '.env'
    env_path.write_text('BOT_TOKEN=from-dotenv\nCHANNEL_USERNAME=@dotenv_channel\n', encoding='utf-8')
    monkeypatch.setenv('BOT_TOKEN', 'from-process')
    monkeypatch.delenv('CHANNEL_USERNAME', raising=False)

    bootstrap = load_project_env(tmp_path)

    assert bootstrap.project_root == tmp_path.resolve()
    assert bootstrap.env_path == env_path
    assert bootstrap.env_found is True
    assert bootstrap.env_loaded is True
    assert bootstrap.bot_token_present is True
    assert bootstrap.channel_username_present is True
    assert os.getenv('BOT_TOKEN') == 'from-process'
    assert os.getenv('CHANNEL_USERNAME') == '@dotenv_channel'
    rendered = '\n'.join(render_bootstrap_diagnostics(bootstrap))
    assert str(env_path) in rendered
    assert 'from-dotenv' not in rendered


def test_load_project_env_accepts_bom_prefixed_bot_token_and_makes_it_visible_to_app_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / '.env'
    token = '123456789:AAabcdefghijklmnopqrstuvwxyz123456'
    env_path.write_text(
        f'BOT_TOKEN={token}\nCHANNEL_USERNAME=@yotoua\n',
        encoding='utf-8-sig',
    )
    monkeypatch.setenv('BOT_TOKEN', '')
    monkeypatch.delenv('CHANNEL_USERNAME', raising=False)

    bootstrap = load_project_env(tmp_path)
    settings = AppSettings.from_env(tmp_path)

    assert bootstrap.env_found is True
    assert bootstrap.env_loaded is True
    assert bootstrap.bot_token_line_found is True
    assert bootstrap.channel_username_line_found is True
    assert bootstrap.bot_token_present is True
    assert bootstrap.channel_username_present is True
    assert os.getenv('BOT_TOKEN') == token
    assert os.getenv('CHANNEL_USERNAME') == '@yotoua'
    assert settings.bot_token == token
    assert settings.channel_username == '@yotoua'
    rendered = '\n'.join(render_bootstrap_diagnostics(bootstrap))
    assert token not in rendered
    assert '@yotoua' not in rendered


def test_app_settings_from_env_reports_missing_required_variable_and_checked_env_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / '.env'
    env_path.write_text('CHANNEL_USERNAME=@dotenv_channel\n', encoding='utf-8')
    monkeypatch.delenv('BOT_TOKEN', raising=False)
    monkeypatch.delenv('CHANNEL_USERNAME', raising=False)

    with pytest.raises(ConfigurationError) as exc_info:
        AppSettings.from_env(tmp_path)

    message = str(exc_info.value)
    assert 'BOT_TOKEN' in message
    assert str(env_path) in message
    assert 'Secret values are not printed.' in message
    assert '@dotenv_channel' not in message
