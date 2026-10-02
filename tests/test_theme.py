from pathlib import Path

APP_SOURCE = Path(__file__).resolve().parents[1] / "flow_cleaning" / "streamlit_app.py"

def test_custom_theme_defines_light_and_dark_tokens():
    source = APP_SOURCE.read_text(encoding="utf-8")
    assert "prefers-color-scheme: dark" in source
    for token in ("--app-bg", "--surface", "--surface-raised", "--ink", "--muted", "--line", "--accent"):
        assert source.count(token) >= 2

def test_custom_styles_do_not_force_a_white_application_background():
    source = APP_SOURCE.read_text(encoding="utf-8")
    assert ".stApp { background: #ffffff" not in source
    assert "background: var(--app-bg)" in source
