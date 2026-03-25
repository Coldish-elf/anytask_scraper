from pathlib import Path

from anytask_scraper.cli import (
    INIT_DEFAULTS,
    _build_parser,
    _ensure_credentials_stub,
    _load_settings,
    _merge_runtime_settings,
    _run_course,
    _save_settings,
)


def test_save_and_load_settings_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    data = {
        "credentials_file": "./credentials.json",
        "session_file": "./.anytask_session.json",
        "status_mode": "errors",
        "default_output": "./output",
        "save_session": True,
        "refresh_session": False,
    }

    _save_settings(str(path), data)
    loaded = _load_settings(str(path))

    assert loaded == data


def test_merge_runtime_settings_uses_saved_defaults() -> None:
    class Args:
        credentials_file = None
        session_file = None
        status_mode = None
        default_output = None
        save_session = None
        refresh_session = None

    args = Args()
    _merge_runtime_settings(
        args,
        {
            "credentials_file": "./credentials.json",
            "session_file": "./.anytask_session.json",
            "status_mode": "errors",
            "default_output": "./output",
            "save_session": False,
            "refresh_session": True,
        },
    )

    assert args.credentials_file == "./credentials.json"
    assert args.session_file == "./.anytask_session.json"
    assert args.status_mode == "errors"
    assert args.default_output == "./output"
    assert args.save_session is False
    assert args.refresh_session is True


def test_merge_runtime_settings_applies_runtime_fallbacks() -> None:
    class Args:
        credentials_file = None
        session_file = None
        status_mode = None
        default_output = None
        save_session = None
        refresh_session = None
        auto_login_session = None

    args = Args()
    _merge_runtime_settings(args, {})

    for key, default in INIT_DEFAULTS.items():
        actual = getattr(args, key)
        assert actual == default, f"{key}: expected {default!r}, got {actual!r}"


def test_settings_init_parses() -> None:
    parser = _build_parser()
    args = parser.parse_args(["settings", "init"])
    assert args.command == "settings"
    assert args.settings_action == "init"


def test_init_defaults_match_expected_values() -> None:
    assert INIT_DEFAULTS["credentials_file"] == "./credentials.json"
    assert INIT_DEFAULTS["session_file"] == str(
        Path.home() / ".config" / "anytask-scraper" / "session.json"
    )
    assert INIT_DEFAULTS["status_mode"] == "errors"
    assert INIT_DEFAULTS["default_output"] == "./output"
    assert INIT_DEFAULTS["save_session"] is True
    assert INIT_DEFAULTS["refresh_session"] is False
    assert INIT_DEFAULTS["auto_login_session"] is True


def test_ensure_credentials_stub_creates_json(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    created = _ensure_credentials_stub(str(path))
    assert created is True
    data = path.read_text(encoding="utf-8")
    assert '"username": "your_username"' in data
    assert '"password": "your_password"' in data


def test_ensure_credentials_stub_does_not_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    path.write_text('{"username":"u","password":"p"}', encoding="utf-8")
    created = _ensure_credentials_stub(str(path))
    assert created is False
    assert path.read_text(encoding="utf-8") == '{"username":"u","password":"p"}'


def test_parser_accepts_filename_for_export_commands() -> None:
    parser = _build_parser()

    args = parser.parse_args(["course", "-c", "1250", "--filename", "report"])
    assert args.filename == "report"

    args = parser.parse_args(["queue", "-c", "1250", "--filename", "queue_export.csv"])
    assert args.filename == "queue_export.csv"

    args = parser.parse_args(["gradebook", "-c", "1250", "--filename", "gb_export"])
    assert args.filename == "gb_export"


def test_run_course_rejects_filename_with_multiple_courses() -> None:
    class Args:
        course = [1250, 1251]
        filename = "report.json"
        output = None
        default_output = None

    try:
        _run_course(Args(), client=object())
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "--filename can only be used with a single --course value" in str(e)
