from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_tabs_are_ordered_with_additional_days_before_validation():
    page = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not page.exception
    assert [tab.label for tab in page.tabs] == [
        "01 Metadata", "02 Day 0", "03 Day 7", "04 Additional days",
        "05 Gate mapping", "06 Validation", "07 Export",
    ]
    assert not page.sidebar.number_input


def test_multiple_additional_days_can_be_added_from_their_own_tab():
    page = AppTest.from_file(str(APP), default_timeout=20)
    page.run()

    selector = next(widget for widget in page.multiselect if widget.label == "Days to add")
    selector.set_value([14, 21]).run()
    next(button for button in page.button if button.label == "Add selected days").click().run()

    assert not page.exception
    assert sorted(page.session_state["additional_days"]) == [14, 21]
    assert [tab.label for tab in page.tabs] == [
        "01 Metadata", "02 Day 0", "03 Day 7", "04 Additional days",
        "05 Day 14", "06 Day 21", "07 Gate mapping", "08 Validation", "09 Export",
    ]
    assert any(button.label == "Process Day 14 files" for button in page.button)
    assert any(button.label == "Process Day 21 files" for button in page.button)