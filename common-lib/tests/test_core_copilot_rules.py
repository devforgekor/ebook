from common_lib.core.copilot_rules import sync_copilot_instructions


def test_sync_copilot_instructions_writes_header_and_rule(tmp_path):
    rule_src = tmp_path / "common-rule.md"
    copilot_instructions = tmp_path / "home" / ".copilot" / "copilot-instructions.md"
    header = "# Header\n\n---\n\n"

    rule_src.write_text("line one\nline two\n", encoding="utf-8")

    sync_copilot_instructions(
        rule_src=rule_src,
        copilot_instructions=copilot_instructions,
        header=header,
    )

    assert copilot_instructions.read_text(encoding="utf-8") == header + "line one\nline two\n"
