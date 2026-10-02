from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "flow_cleaning"
DECORATIVE_SYMBOLS = set("✅❌⚠ℹ🔍🔗📊📋📄📁📝🧬👥🔬🧹✂🗑💡🚀✨🎯✏👀🔤📈🧩📥📤📦🌳📷🧾🎛🔄🔒🔓🎉🏷🗂✓✗")

def test_user_facing_source_has_no_decorative_emoji():
    offenders = {}
    for path in SOURCE.rglob("*.py"):
        found = sorted(DECORATIVE_SYMBOLS.intersection(path.read_text(encoding="utf-8")))
        if found: offenders[str(path.relative_to(SOURCE))] = found
    assert offenders == {}
