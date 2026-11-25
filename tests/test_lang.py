#!/usr/bin/env python3
"""The launcher's translations (scripts/lang.py, port/lang): the catalog matches the sources, each language file has
every text of the catalog and no other, a translation keeps the English's placeholders, and the exe carries every
language (app.rc, i18n.cpp).

A text without a translation is not a fault (the launcher shows the English); a new text in the sources without
`lang.py extract` and `lang.py update` is.

Usage:
    python tests/test_lang.py
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lang  # noqa: E402


def entries(path):
    return [e for e in lang.read_po(str(path)) if e[1]]


class Catalog(unittest.TestCase):
    def test_catalog_is_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "launcher.pot")
            lang.extract(out)
            now = [e[1] for e in entries(out)]
        kept = [e[1] for e in entries(ROOT / "port" / "lang" / "launcher.pot")]
        self.assertEqual(now, kept, "port/lang/launcher.pot is behind the sources: run scripts/lang.py extract, then update")

    def test_languages(self):
        pot = [e[1] for e in entries(ROOT / "port" / "lang" / "launcher.pot")]
        for code in lang.CODES:
            with self.subTest(code=code):
                po = entries(ROOT / "port" / "lang" / (code + ".po"))
                self.assertEqual([e[1] for e in po], pot, "%s.po: run scripts/lang.py update" % code)
                for _, msgid, msgstr in po:
                    if msgstr:
                        self.assertIsNone(lang.fault(msgid, msgstr), "%s.po: %r" % (code, msgid))

    def test_the_exe_carries_each(self):
        rc = (ROOT / "port" / "app.rc").read_text(encoding="utf-8")
        cpp = (ROOT / "port" / "i18n.cpp").read_text(encoding="utf-8")
        for code in lang.CODES:
            m = re.search(r"^(\d+) RCDATA \"lang\\\\%s\.po\"" % re.escape(code), rc, re.M)
            self.assertTrue(m, "app.rc has no %s.po" % code)
            self.assertIn('{ "%s", %s }' % (code, m.group(1)), cpp, "i18n.cpp reads %s.po by another number" % code)


if __name__ == "__main__":
    unittest.main()
