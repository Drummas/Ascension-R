/*
 * Ascension-R -- the paths kept in ascension-r.ini are the program's own, relative to its folder
 *
 * A copy of the program is a folder: ascension-r.ini, the game's decrypted ELF, the game's built code, the shader
 * caches, the saves and the logs all live in it (default_settings_path in main.cpp). For the folder to work from
 * anywhere -- moved, copied to another drive or to another PC -- the paths it keeps are written relative to it:
 *
 *     [paths]
 *     elf = vfs\PS3_GAME\USRDIR\GOWA.elf      the game's folder and RPCS3 are the player's: outside it, absolute
 *     vfs = vfs
 *     hdd0 = gamedata\dev_hdd0
 *     [graphics]
 *     shader_cache = d3d12_shader_cache.bin
 *
 * A path inside the folder is kept with no drive and no leading slash (ppath_keep), and every reader makes it whole
 * again from the folder the settings file is in (ppath_use, ppath_setting). An absolute path is left as it is, so a
 * settings file written by hand, or by an older version, still reads the same.
 *
 * The helper is header-only: every file of the port that keeps or reads such a path uses it, and the test builds it
 * with PPATH_NO_SETTINGS (tests/test_portable_paths.py).
 */
#ifndef ASCENSION_R_PORTABLE_PATHS_H
#define ASCENSION_R_PORTABLE_PATHS_H

#include <stdio.h>
#include <string.h>
#include <wchar.h>

#ifndef PPATH_MAX
#define PPATH_MAX 1100
#endif

#ifndef _WIN32

/* Elsewhere nothing is compiled for players (the release is Windows x64 only): a path is used as it is. */
#include "ps3emu/ps3_settings.h"
static inline const char* ppath_setting(const char* section, const char* key, const char* env, const char* def,
                                        char* out, size_t n)
{
    const char* v = ps3_settings_str(section, key, env, def);
    if (!v) v = "";
    if (n) snprintf(out, n, "%s", v);
    return out;
}

#else

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

/* Whether a path names a place by itself: "C:\...", "\\server\share\...", or "/...". */
static inline int ppath_absolute(const wchar_t* p)
{
    return p && *p && (p[0] == L'\\' || p[0] == L'/' || (p[1] == L':'));
}

static inline void ppath_backslashes(wchar_t* p) { for (; *p; p++) if (*p == L'/') *p = L'\\'; }

static inline void ppath_copy_w(wchar_t* out, size_t n, const wchar_t* from)
{
    if (!n) return;
    if (!from) { out[0] = 0; return; }
    wcsncpy(out, from, n - 1);
    out[n - 1] = 0;
}

/* UTF-8 into wide, "" when it does not fit. */
static inline int ppath_wide(const char* utf8, wchar_t* out, size_t n)
{
    out[0] = 0;
    if (!utf8 || !*utf8 || !n) return 0;
    if (MultiByteToWideChar(CP_UTF8, 0, utf8, -1, out, (int)n) <= 0) out[0] = 0;
    return out[0] != 0;
}

/* Wide into UTF-8; `n` is in bytes, and a path of PPATH_MAX characters needs three times that. */
static inline void ppath_utf8(const wchar_t* wide, char* out, size_t n)
{
    if (n) out[0] = 0;
    if (!wide || !*wide || !n) return;
    if (WideCharToMultiByte(CP_UTF8, 0, wide, -1, out, (int)n, NULL, NULL) <= 0) out[0] = 0;
}

/* The absolute path, worked out from the current directory when it is relative and with "." and ".." taken out. */
static inline void ppath_full(const wchar_t* p, wchar_t* out, size_t n)
{
    out[0] = 0;
    if (!p || !*p) return;
    if (!GetFullPathNameW(p, (DWORD)n, out, NULL)) out[0] = 0;
    ppath_backslashes(out);
}

/* `path` as the settings keep it under `root`: relative to it when it is inside, absolute when it is not. */
static inline void ppath_keep_in(const wchar_t* root, const wchar_t* path, wchar_t* out, size_t n)
{
    out[0] = 0;
    if (!path || !*path) return;
    wchar_t full[PPATH_MAX];
    ppath_full(path, full, PPATH_MAX);
    if (!full[0]) { ppath_copy_w(out, n, path); return; }
    const size_t rl = root ? wcslen(root) : 0;
    if (rl < PPATH_MAX && !_wcsnicmp(full, root, rl) && full[rl] == L'\\' && full[rl + 1]) {
        ppath_copy_w(out, n, full + rl + 1);   /* the way down from the root */
        return;
    }
    ppath_copy_w(out, n, full);
}

/* A kept path, made whole again: the root, then the way down; an absolute one as it is. */
static inline void ppath_use_in(const wchar_t* root, const wchar_t* kept, wchar_t* out, size_t n)
{
    out[0] = 0;
    if (!kept || !*kept) return;
    if (ppath_absolute(kept) || !root || !*root) { ppath_copy_w(out, n, kept); ppath_backslashes(out); return; }
    swprintf(out, n, L"%ls\\%ls", root, kept);
    ppath_backslashes(out);
}

#ifndef PPATH_NO_SETTINGS
#include "ps3emu/ps3_settings.h"

/* The folder ascension-r.ini is in (the program's own), else the executable's: the root the paths are kept against. */
static inline int ppath_root(wchar_t* out, size_t n)
{
    out[0] = 0;
    const char* sp = ps3_settings_path();
    if (sp && *sp) {
        char dir[PPATH_MAX];
        snprintf(dir, sizeof dir, "%s", sp);
        char* slash = strrchr(dir, '\\');
        if (!slash) slash = strrchr(dir, '/');
        if (slash) slash[1] = 0; else dir[0] = 0;
        ppath_wide(dir, out, n);
        if (out[0]) {
            wchar_t* s = wcsrchr(out, L'\\');
            if (!s) s = wcsrchr(out, L'/');
            if (s) *s = 0;
            ppath_backslashes(out);
        }
    }
    if (!out[0]) {
        const DWORD len = GetModuleFileNameW(NULL, out, (DWORD)n);
        if (!len || len >= n) { out[0] = 0; return 0; }
        wchar_t* s = wcsrchr(out, L'\\');
        if (s) *s = 0;
    }
    return out[0] != 0;
}

/* A path as the settings keep it: relative to the program's folder for one inside it, absolute otherwise. */
static inline void ppath_keep(const wchar_t* path, wchar_t* out, size_t n)
{
    wchar_t root[PPATH_MAX];
    out[0] = 0;
    if (!path || !*path) return;
    if (!ppath_root(root, PPATH_MAX)) { ppath_copy_w(out, n, path); return; }
    ppath_keep_in(root, path, out, n);
}

/* The same, for a file of the settings (they are UTF-8). */
static inline void ppath_keep_u8(const wchar_t* path, char* out, size_t n)
{
    wchar_t kept[PPATH_MAX];
    if (n) out[0] = 0;
    ppath_keep(path, kept, PPATH_MAX);
    ppath_utf8(kept, out, n);
}

/* A kept path, made whole: what the file system and the runtime take. */
static inline void ppath_use(const wchar_t* kept, wchar_t* out, size_t n)
{
    wchar_t root[PPATH_MAX];
    out[0] = 0;
    if (!kept || !*kept) return;
    if (ppath_absolute(kept) || !ppath_root(root, PPATH_MAX)) { ppath_copy_w(out, n, kept); return; }
    ppath_use_in(root, kept, out, n);
}

static inline void ppath_use_u8(const char* kept, wchar_t* out, size_t n)
{
    wchar_t w[PPATH_MAX];
    out[0] = 0;
    if (!ppath_wide(kept, w, PPATH_MAX)) return;
    ppath_use(w, out, n);
}

/* section.key of the settings (or its environment variable), as a path the file system takes; out is at least
 * three times PPATH_MAX bytes. */
static inline const char* ppath_setting(const char* section, const char* key, const char* env, const char* def,
                                        char* out, size_t n)
{
    if (n) out[0] = 0;
    const char* v = ps3_settings_str(section, key, env, def);
    wchar_t kept[PPATH_MAX], full[PPATH_MAX];
    if (!ppath_wide(v, kept, PPATH_MAX)) return out;
    ppath_use(kept, full, PPATH_MAX);
    ppath_utf8(full, out, n);
    return out;
}

static inline const wchar_t* ppath_setting_w(const char* section, const char* key, const char* env, const char* def,
                                             wchar_t* out, size_t n)
{
    out[0] = 0;
    const char* v = ps3_settings_str(section, key, env, def);
    wchar_t kept[PPATH_MAX];
    if (!ppath_wide(v, kept, PPATH_MAX)) return out;
    ppath_use(kept, out, n);
    return out;
}

/* graphics.shader_cache: a path of the program's own, or "off" (no cache at all), which stays as it is. */
static inline const char* ppath_shader_cache(char* out, size_t n)
{
    const char* v = ps3_settings_str("graphics", "shader_cache", "D3D12_SHADER_CACHE", NULL);
    if (!v || !*v || ps3_settings_ieq(v, "off")) {
        if (n) snprintf(out, n, "%s", v ? v : "");
        return out;
    }
    return ppath_setting("graphics", "shader_cache", "D3D12_SHADER_CACHE", NULL, out, n);
}

#endif /* PPATH_NO_SETTINGS */
#endif /* _WIN32 */

#endif /* ASCENSION_R_PORTABLE_PATHS_H */
