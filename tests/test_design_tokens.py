import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import design_tokens


class DesignTokens(unittest.TestCase):
    def setUp(self):
        self.tokens = design_tokens.load()

    def test_style_css_matches_tokens(self):
        # the website's colours come from design/tokens.json; edit there, then run the script
        self.assertEqual(design_tokens.main(["--check"]), 0)

    def test_every_colour_is_hex(self):
        for name, pair in self.tokens["colors"].items():
            self.assertIn("dark", pair, name)
            for value in pair.values():
                self.assertRegex(value, r"^#[0-9A-Fa-f]{6}$", name)

    def test_swift_has_every_colour(self):
        out = design_tokens.swift(self.tokens)
        self.assertIn("enum AccretionTokens {", out)
        self.assertIn("static let accent2: (dark: UInt32, light: UInt32) = (0x22D3EE, 0x0E8FB0)", out)
        # dark-only colours use the same value in light mode
        self.assertIn("static let onAccent: (dark: UInt32, light: UInt32) = (0xFFFFFF, 0xFFFFFF)", out)
        self.assertIn("static let gridSize: CGFloat = 28", out)
        self.assertEqual(len(re.findall(r"static let \w+: \(dark: UInt32", out)), len(self.tokens["colors"]))

    def test_css_block_is_replaced_once(self):
        block = design_tokens.css(self.tokens)
        text = "a {}\n" + block + "\nb {}\n"
        self.assertEqual(design_tokens.apply_css(text, block), text)


if __name__ == "__main__":
    unittest.main()
