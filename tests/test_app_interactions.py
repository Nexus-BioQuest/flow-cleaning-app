from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"

def test_lock_and_unlock_defaults_keep_the_full_app_rendered():
    page = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not page.exception
    assert [tab.label for tab in page.tabs] == [
        "01  Metadata", "02  Day 0", "03  Day 7",
        "04  Gate mapping", "05  Validation", "06  Export",
    ]

    page.sidebar.button[0].click().run()
    assert not page.exception
    assert page.title[0].value == "Flow Cytometry Data Preparation"
    assert page.session_state["defaults_set"] is True
    assert any(button.label == "Unlock defaults" for button in page.sidebar.button)
    assert all(field.disabled for field in page.sidebar.number_input)

    next(button for button in page.sidebar.button if button.label == "Unlock defaults").click().run()
    assert not page.exception
    assert page.title[0].value == "Flow Cytometry Data Preparation"
    assert page.session_state["defaults_set"] is False
    assert all(not field.disabled for field in page.sidebar.number_input)
