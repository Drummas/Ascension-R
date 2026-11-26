#!/usr/bin/env python3
"""portable_paths.h: the paths ascension-r.ini keeps are relative to the program's folder, and made whole again.

Builds a driver with clang-cl (PPATH_NO_SETTINGS: the helpers that read the settings are left out, so nothing of the
runtime is linked) and checks what a path under the folder is kept as, what one outside it is kept as, and what each
is made back into: a copy of the folder works moved, on another drive, or on another PC.

Usage:
    python tests/test_portable_paths.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DRIVER = r'''
#include "portable_paths.h"
#include <stdio.h>
#include <string.h>

static int failed;

static void is(const wchar_t* got, const wchar_t* want, const char* what)
{
    if (!wcscmp(got, want)) return;
    printf("  %s: got \"%ls\", want \"%ls\"\n", what, got, want);
    failed++;
}

static void kept_is(const wchar_t* root, const wchar_t* path, const wchar_t* want, const char* what)
{
    wchar_t kept[PPATH_MAX];
    ppath_keep_in(root, path, kept, PPATH_MAX);
    is(kept, want, what);
}

static void used_is(const wchar_t* root, const wchar_t* kept, const wchar_t* want, const char* what)
{
    wchar_t used[PPATH_MAX];
    ppath_use_in(root, kept, used, PPATH_MAX);
    is(used, want, what);
}

int wmain(void)
{
    const wchar_t* root = L"C:\\Games\\Ascension-R";

    /* Inside the folder: the way down from it, with no drive and no leading slash. */
    kept_is(root, L"C:\\Games\\Ascension-R\\vfs", L"vfs", "the vfs folder");
    kept_is(root, L"C:\\Games\\Ascension-R\\gamedata\\dev_hdd0", L"gamedata\\dev_hdd0", "the saves' folder");
    kept_is(root, L"C:\\Games\\Ascension-R\\d3d12_shader_cache.bin", L"d3d12_shader_cache.bin", "a file beside the exe");

    /* Outside it: absolute, as it has to be. The game's folder and RPCS3 are the player's, and are only read. */
    kept_is(root, L"D:\\RPCS3\\dev_hdd0\\game\\NPUA80918", L"D:\\RPCS3\\dev_hdd0\\game\\NPUA80918", "the game's folder");
    kept_is(root, L"C:\\Games\\ascension-r-kit\\vfs", L"C:\\Games\\ascension-r-kit\\vfs", "a folder whose name starts the same");

    /* Either slash read, one written; "." and ".." taken out. */
    kept_is(root, L"C:/Games/Ascension-R/vfs", L"vfs", "forward slashes");
    kept_is(root, L"C:\\Games\\Ascension-R\\logs\\..\\vfs", L"vfs", "a way back up");
    kept_is(root, L"C:\\Games\\Ascension-R", L"C:\\Games\\Ascension-R", "the folder itself, not a file under it");

    /* Made whole again: the folder, then the way down. An absolute path is left as it is. */
    used_is(root, L"vfs", L"C:\\Games\\Ascension-R\\vfs", "the vfs folder, whole");
    used_is(root, L"gamedata\\dev_hdd0", L"C:\\Games\\Ascension-R\\gamedata\\dev_hdd0", "the saves' folder, whole");
    used_is(root, L"D:\\RPCS3\\rpcs3.exe", L"D:\\RPCS3\\rpcs3.exe", "an absolute path");
    used_is(root, L"vfs/PS3_GAME", L"C:\\Games\\Ascension-R\\vfs\\PS3_GAME", "a kept path with forward slashes");
    used_is(root, L"", L"", "nothing");

    /* The same in UTF-8, as the settings file keeps them (a folder or a game's folder may have any name). */
    {
        const wchar_t* named = L"C:\\Jogos\\Ascens\x00E3o-R\\vfs";
        wchar_t kept[PPATH_MAX], used[PPATH_MAX];
        char utf8[PPATH_MAX * 4];
        wchar_t back[PPATH_MAX];
        ppath_keep_in(L"C:\\Jogos\\Ascens\x00E3o-R", named, kept, PPATH_MAX);
        is(kept, L"vfs", "a folder with an accent");
        ppath_utf8(kept, utf8, sizeof utf8);
        ppath_wide(utf8, back, PPATH_MAX);
        is(back, L"vfs", "a kept path through UTF-8");
        ppath_wide("vfs/PS3_GAME", back, PPATH_MAX);
        ppath_use_in(L"C:\\Jogos\\Ascens\x00E3o-R", back, used, PPATH_MAX);
        is(used, L"C:\\Jogos\\Ascens\x00E3o-R\\vfs\\PS3_GAME", "a whole path with an accent");
    }

    if (failed) {
        printf("%d failed\n", failed);
        return 1;
    }
    printf("portable_paths: ok\n");
    return 0;
}
'''


@unittest.skipUnless(os.name == "nt", "Windows only")
class PortablePaths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="portable-paths-")
        sys.path.insert(0, str(ROOT / "scripts"))
        import gowa
        cls.gowa = gowa
        env = gowa.toolchain_env()
        clang = shutil.which("clang-cl", path=env.get("PATH"))
        if not clang:
            raise unittest.SkipTest("no clang-cl")
        cls.exe = os.path.join(cls.tmp, "t.exe")
        src = os.path.join(cls.tmp, "t.cpp")
        Path(src).write_text(DRIVER, encoding="utf-8")
        cmd = [clang, "/nologo", "/O1", "/EHsc", "/std:c++17", "/DPPATH_NO_SETTINGS", "/I" + str(ROOT / "port"),
               src, "/Fe" + cls.exe, "/Fo" + cls.tmp + "\\"]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cls.tmp)
        if r.returncode:
            raise AssertionError(r.stdout + r.stderr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_paths(self):
        r = subprocess.run([self.exe], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
