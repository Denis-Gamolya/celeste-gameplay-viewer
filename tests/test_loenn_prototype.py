"""Check the development adapter's room identity and output boundaries."""

import tempfile
import unittest
from pathlib import Path

from tools.prototype_loenn_browser import (
    connect_loenn_document,
    script_json,
    validate_output,
)


def generated_structure():
    """Return only the generated markers the adapter must recognize."""
    return (
        '<html><head></head><body><rect data-idx="0"/>'
        '<rect data-idx="1"/><script>fitToWindow(); apply();\n\n// next phase'
        "</script></body></html>"
    )


class LoennPrototypeTests(unittest.TestCase):
    def test_bridge_uses_full_names_in_source_order(self):
        document = connect_loenn_document(
            generated_structure(), ["lvl_s1", "lvl_12"], "test-channel"
        )
        self.assertIn('const names = ["lvl_s1","lvl_12"];', document)
        self.assertIn("requestAnimationFrame", document)
        self.assertIn("celeste:open-room", document)
        self.assertIn("connect-src 'none'", document)

    def test_ambiguous_or_changed_targets_are_rejected(self):
        for names in (["lvl_s1"], ["lvl_s1", "lvl_s1"]):
            with self.assertRaises(ValueError):
                connect_loenn_document(generated_structure(), names, "channel")
        with self.assertRaises(ValueError):
            connect_loenn_document(
                generated_structure().replace('data-idx="1"', 'data-idx="2"'),
                ["lvl_s1", "lvl_12"],
                "channel",
            )
        with self.assertRaises(ValueError):
            connect_loenn_document(
                generated_structure().replace(
                    "fitToWindow(); apply();", "changed();"
                ),
                ["lvl_s1", "lvl_12"],
                "channel",
            )

    def test_inline_data_cannot_close_the_enclosing_script(self):
        encoded = script_json({"room": "</script><script>bad()</script>&"})
        self.assertNotIn("<", encoded)
        self.assertNotIn(">", encoded)
        self.assertNotIn("&", encoded)

    def test_generated_files_stay_outside_the_game(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "Celeste/Mods/MyMod"
            workspace.mkdir(parents=True)
            validate_output(workspace, root / "output")
            for output in (workspace, root / "Celeste/Content/Maps"):
                with self.assertRaises(ValueError):
                    validate_output(workspace, output)
