/*
 * The mods folder (mods.h): what is in it, in which order, and the folders the game's file system takes for the
 * mods that are on (PS3_MODS_DIRS, ps3recomp's runtime/syscalls/vfs_mods.h).
 */
#include "mods.h"

#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <wctype.h>
#include <algorithm>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include "third_party/zlib/zlib.h"
#include "ps3emu/ps3_settings.h"

namespace {

std::string u8(const std::wstring& w)
{
    if (w.empty()) return std::string();
    const int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), NULL, 0, NULL, NULL);
    std::string s((size_t)(n > 0 ? n : 0), '\0');
    if (n > 0) WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), &s[0], n, NULL, NULL);
    return s;
}

std::wstring wide(const char* s, int len = -1, UINT cp = CP_UTF8)
{
    if (!s || !len) return std::wstring();
    const int n = MultiByteToWideChar(cp, 0, s, len, NULL, 0);
    if (n <= 0) return std::wstring();
    std::wstring w((size_t)n, L'\0');
    MultiByteToWideChar(cp, 0, s, len, &w[0], n);
    if (len < 0 && !w.empty() && w.back() == L'\0') w.pop_back();
    return w;
}

std::wstring upper(std::wstring s)
{
    for (wchar_t& c : s) c = (wchar_t)towupper(c);
    return s;
}

bool same(const std::wstring& a, const std::wstring& b) { return upper(a) == upper(b); }

bool is_dir(const std::wstring& p)
{
    const DWORD a = GetFileAttributesW(p.c_str());
    return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}
bool is_file(const std::wstring& p)
{
    const DWORD a = GetFileAttributesW(p.c_str());
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

/* A folder's names, folders and files apart, sorted without regard to case. */
void list_dir(const std::wstring& dir, std::vector<std::wstring>* dirs, std::vector<std::wstring>* files)
{
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileExW((dir + L"\\*").c_str(), FindExInfoBasic, &fd, FindExSearchNameMatch, NULL, 0);
    if (h == INVALID_HANDLE_VALUE) return;
    do {
        if (!wcscmp(fd.cFileName, L".") || !wcscmp(fd.cFileName, L"..")) continue;
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) { if (dirs) dirs->push_back(fd.cFileName); }
        else if (files) files->push_back(fd.cFileName);
    } while (FindNextFileW(h, &fd));
    FindClose(h);
    auto by_name = [](const std::wstring& a, const std::wstring& b) { return upper(a) < upper(b); };
    if (dirs) std::sort(dirs->begin(), dirs->end(), by_name);
    if (files) std::sort(files->begin(), files->end(), by_name);
}

/* Every file under dir, relative to it, in upper case with '/': as vfs_mods.h walks it (32 folders deep at most). */
void walk(const std::wstring& dir, const std::wstring& rel, std::vector<std::wstring>* out, int depth)
{
    if (depth > 32 || out->size() >= 500000) return;
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileExW((dir + L"\\*").c_str(), FindExInfoBasic, &fd, FindExSearchNameMatch, NULL, 0);
    if (h == INVALID_HANDLE_VALUE) return;
    do {
        if (!wcscmp(fd.cFileName, L".") || !wcscmp(fd.cFileName, L"..")) continue;
        const std::wstring r = rel.empty() ? std::wstring(fd.cFileName) : rel + L"/" + fd.cFileName;
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) walk(dir + L"\\" + fd.cFileName, r, out, depth + 1);
        else out->push_back(upper(r));
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}

std::wstring settings_dir(void)
{
    std::wstring here = wide(ps3_settings_path());
    for (wchar_t& c : here) if (c == L'/') c = L'\\';
    const size_t s = here.find_last_of(L'\\');
    if (s != std::wstring::npos) return here.substr(0, s);
    wchar_t exe[MAX_PATH];
    const DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
    if (n && n < MAX_PATH) {
        if (wchar_t* e = wcsrchr(exe, L'\\')) *e = 0;
        return exe;
    }
    return L".";
}

/* "a|b|c" of the settings, as names. */
std::vector<std::wstring> names_of(const char* v)
{
    std::vector<std::wstring> out;
    if (!v) return out;
    const std::wstring w = wide(v);
    size_t at = 0;
    while (at <= w.size()) {
        size_t e = w.find(L'|', at);
        if (e == std::wstring::npos) e = w.size();
        std::wstring n = w.substr(at, e - at);
        while (!n.empty() && iswspace(n.front())) n.erase(n.begin());
        while (!n.empty() && iswspace(n.back())) n.pop_back();
        if (!n.empty()) out.push_back(n);
        at = e + 1;
    }
    return out;
}

/* A value of mod.ini as it is kept: control characters as spaces, at most max bytes, cut where a character starts. */
std::string clip(const char* v, size_t max)
{
    std::string s;
    for (const char* p = v; *p; p++) s += (unsigned char)*p < 0x20 ? ' ' : *p;
    if (s.size() > max) {
        size_t n = max;
        while (n > 0 && ((unsigned char)s[n] & 0xC0) == 0x80) n--;
        s.resize(n);
        s += "\xE2\x80\xA6";   /* ... */
    }
    return s;
}

void read_ini(const std::wstring& path, ModInfo* m)
{
    FILE* f = _wfopen(path.c_str(), L"rb");
    if (!f) return;
    std::vector<char> b(65536);
    const size_t n = fread(b.data(), 1, b.size() - 1, f);
    fclose(f);
    b[n] = 0;
    char* p = b.data();
    if (n >= 3 && (unsigned char)p[0] == 0xEF && (unsigned char)p[1] == 0xBB && (unsigned char)p[2] == 0xBF) p += 3;
    int in_mod = 0;
    while (*p) {
        char* e = p + strcspn(p, "\r\n");
        char* next = *e ? e + 1 : e;
        *e = 0;
        char* s = p;
        while (*s == ' ' || *s == '\t') s++;
        char* t = s + strlen(s);
        while (t > s && (t[-1] == ' ' || t[-1] == '\t')) *--t = 0;
        if (*s == '[') {
            in_mod = !_stricmp(s, "[mod]");
        } else if (in_mod && *s && *s != ';' && *s != '#') {
            if (char* eq = strchr(s, '=')) {
                char* ke = eq;
                while (ke > s && (ke[-1] == ' ' || ke[-1] == '\t')) ke--;
                *ke = 0;
                char* v = eq + 1;
                while (*v == ' ' || *v == '\t') v++;
                const size_t vn = strlen(v);
                if (vn >= 2 && v[0] == '"' && v[vn - 1] == '"') { v[vn - 1] = 0; v++; }
                if (!_stricmp(s, "name")) m->name = clip(v, 80);
                else if (!_stricmp(s, "version")) m->version = clip(v, 32);
                else if (!_stricmp(s, "author")) m->author = clip(v, 80);
                else if (!_stricmp(s, "description")) m->desc = clip(v, 300);
            }
        }
        p = next;
    }
}

const wchar_t* const k_direct[] = { L"files", L"USRDIR", L"PS3_GAME\\USRDIR" };
const char* const k_later[] = { "archive", "textures", "text", "patches" };

/* Whether a folder is a mod's own: its mod.ini, or a folder of one it knows. The old text tool's mod folder was
 * dev_hdd0 itself. */
bool mod_like(const std::wstring& dir, const std::wstring& id)
{
    if (is_file(dir + L"\\mod.ini") || is_dir(dir + L"\\dev_hdd0\\game")) return true;
    if (same(id, L"dev_hdd0") && is_dir(dir + L"\\game")) return true;
    for (const wchar_t* d : k_direct) if (is_dir(dir + L"\\" + d)) return true;
    for (const char* d : k_later) if (is_dir(dir + L"\\" + wide(d))) return true;
    return false;
}

/* A file beside a mod's own that the game has no use for: its mod.ini, a read-me, a picture of it. */
bool beside(const std::wstring& name)
{
    const std::wstring n = upper(name);
    if (n == L"MOD.INI" || !n.compare(0, 6, L"README")) return true;
    static const wchar_t* const ext[] = { L".TXT", L".MD", L".URL", L".NFO", L".PDF", L".PNG", L".JPG", L".JPEG",
                                          L".GIF", L".WEBP" };
    for (const wchar_t* e : ext) {
        const size_t k = wcslen(e);
        if (n.size() > k && !n.compare(n.size() - k, k, e)) return true;
    }
    return false;
}

/* The folders the game's own USRDIR has: a mod that brings one is laid out as USRDIR is. */
bool game_folder(const std::wstring& name)
{
    const std::wstring n = upper(name);
    return n == L"BUILD" || n == L"DATA" || n == L"ICONS";
}

/* Where a mod's own files start: dir, or the one folder it holds, two down at most (a zip of a folder, unpacked
 * into a folder of its own). Not into a folder of the game's, nor past a file of the mod's. */
std::wstring mod_root(const std::wstring& dir, const std::wstring& id)
{
    std::wstring r = dir;
    for (int i = 0; i < 2; i++) {
        if (mod_like(r, id)) return r;
        std::vector<std::wstring> ds, fs;
        list_dir(r, &ds, &fs);
        if (ds.size() != 1 || game_folder(ds[0])) break;
        bool own = false;
        for (const std::wstring& f : fs) own |= !beside(f);
        if (own) break;
        r += L"\\" + ds[0];
    }
    return r;
}

void layout(ModInfo* m)
{
    const std::wstring& r = m->root;
    for (const wchar_t* d : k_direct)
        if (is_dir(r + L"\\" + d)) m->usrdirs.push_back(r + L"\\" + d);
    auto titles = [&](const std::wstring& game) {
        std::vector<std::wstring> ids;
        list_dir(game, &ids, NULL);
        for (const std::wstring& id : ids)
            if (is_dir(game + L"\\" + id + L"\\USRDIR")) m->usrdirs.push_back(game + L"\\" + id + L"\\USRDIR");
    };
    if (is_dir(r + L"\\dev_hdd0\\game")) titles(r + L"\\dev_hdd0\\game");
    if (same(m->id, L"dev_hdd0") && is_dir(r + L"\\game")) titles(r + L"\\game");
    for (const char* d : k_later)
        if (is_dir(r + L"\\" + wide(d))) m->later.push_back(d);
    /* None of those: the folder is laid out as USRDIR is, its files the game's. */
    if (m->usrdirs.empty() && m->later.empty()) {
        std::vector<std::wstring> ds, fs;
        list_dir(r, &ds, &fs);
        bool any = !ds.empty();
        for (const std::wstring& f : fs) any |= !beside(f);
        if (any) m->usrdirs.push_back(r);
    }
}

/* --- a zip, unpacked ------------------------------------------------------------------------------------------- */

uint32_t rd16(const unsigned char* p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8; }
uint32_t rd32(const unsigned char* p) { return rd16(p) | rd16(p + 2) << 16; }

/* A name inside the zip as a path under the folder it is unpacked into, or "" when it would not be one: no
 * folder up or from the root, no drive, nothing Windows would change or refuse. */
std::wstring zip_rel(const std::wstring& name)
{
    std::wstring out;
    size_t at = 0;
    if (name.empty() || name[0] == L'/' || name[0] == L'\\') return std::wstring();
    while (at < name.size()) {
        size_t e = name.find_first_of(L"/\\", at);
        if (e == std::wstring::npos) e = name.size();
        const std::wstring part = name.substr(at, e - at);
        at = e + 1;
        if (part.empty()) continue;
        if (part == L"." || part == L"..") return std::wstring();
        for (wchar_t c : part)
            if (c < 0x20 || wcschr(L"<>:\"|?*", c)) return std::wstring();
        if (part.back() == L'.' || part.back() == L' ') return std::wstring();
        std::wstring base = upper(part.substr(0, part.find(L'.')));
        static const wchar_t* const dev[] = { L"CON", L"PRN", L"AUX", L"NUL", L"COM1", L"COM2", L"COM3", L"COM4",
                                              L"COM5", L"COM6", L"COM7", L"COM8", L"COM9", L"LPT1", L"LPT2", L"LPT3",
                                              L"LPT4", L"LPT5", L"LPT6", L"LPT7", L"LPT8", L"LPT9" };
        for (const wchar_t* d : dev) if (base == d) return std::wstring();
        if (!out.empty()) out += L'\\';
        out += part;
    }
    return out;
}

bool make_dirs(const std::wstring& base, const std::wstring& rel)
{
    size_t at = 0;
    while ((at = rel.find(L'\\', at)) != std::wstring::npos) {
        const std::wstring d = base + L"\\" + rel.substr(0, at);
        if (!CreateDirectoryW(d.c_str(), NULL) && GetLastError() != ERROR_ALREADY_EXISTS) return false;
        at++;
    }
    return true;
}

/* The zip's files into the folder `to`, which is made. "" when done, else why not. */
std::string unzip(const std::wstring& zip, const std::wstring& to)
{
    FILE* f = _wfopen(zip.c_str(), L"rb");
    if (!f) return "it could not be opened";
    struct Closer { FILE* f; ~Closer() { fclose(f); } } closer{ f };
    _fseeki64(f, 0, SEEK_END);
    const long long size = _ftelli64(f);
    if (size < 22) return "it is not a zip file";
    const long long tail_n = size < 65557 ? size : 65557;
    std::vector<unsigned char> tail((size_t)tail_n);
    _fseeki64(f, size - tail_n, SEEK_SET);
    if (fread(tail.data(), 1, tail.size(), f) != tail.size()) return "it could not be read";
    long long eocd = -1;
    for (long long i = tail_n - 22; i >= 0; i--)
        if (rd32(&tail[(size_t)i]) == 0x06054B50u) { eocd = i; break; }
    if (eocd < 0) return "it is not a zip file";
    const unsigned char* e = &tail[(size_t)eocd];
    const uint32_t count = rd16(e + 10), cd_size = rd32(e + 12), cd_at = rd32(e + 16);
    if (rd16(e + 4) || rd16(e + 6)) return "it is a zip of several parts";
    if (count == 0xFFFF || cd_size == 0xFFFFFFFFu || cd_at == 0xFFFFFFFFu) return "it is a Zip64 file: zip it again without";
    if ((long long)cd_at + cd_size > size || cd_size > (64u << 20)) return "it is not a zip file";
    std::vector<unsigned char> cd(cd_size);
    _fseeki64(f, cd_at, SEEK_SET);
    if (cd_size && fread(cd.data(), 1, cd.size(), f) != cd.size()) return "it could not be read";
    if (!CreateDirectoryW(to.c_str(), NULL) && GetLastError() != ERROR_ALREADY_EXISTS) return "no folder could be made for it";
    std::vector<unsigned char> in(1 << 16), out(1 << 16);
    size_t at = 0;
    for (uint32_t k = 0; k < count; k++) {
        if (at + 46 > cd.size() || rd32(&cd[at]) != 0x02014B50u) return "its list of files is damaged";
        const unsigned char* c = &cd[at];
        const uint32_t flags = rd16(c + 8), method = rd16(c + 10), crc = rd32(c + 16), csize = rd32(c + 20),
                       usize = rd32(c + 24), nn = rd16(c + 28), xn = rd16(c + 30), mn = rd16(c + 32),
                       local = rd32(c + 42);
        if (at + 46 + nn > cd.size()) return "its list of files is damaged";
        const std::wstring name = wide((const char*)c + 46, (int)nn, (flags & 0x800) ? CP_UTF8 : 437);
        at += 46 + nn + xn + mn;
        if (!name.empty() && (name.back() == L'/' || name.back() == L'\\')) continue;   /* a folder */
        const std::wstring rel = zip_rel(name);
        if (rel.empty()) return "it names a file outside its folder, or one Windows cannot have: " + u8(name);
        if (flags & 1) return "it is encrypted";
        if (method != 0 && method != 8) return "it is compressed in a way this build does not read (" + u8(name) + ")";
        if (csize == 0xFFFFFFFFu || usize == 0xFFFFFFFFu) return "it is a Zip64 file: zip it again without";
        unsigned char lh[30];
        _fseeki64(f, local, SEEK_SET);
        if (fread(lh, 1, 30, f) != 30 || rd32(lh) != 0x04034B50u) return "its files are damaged";
        _fseeki64(f, (long long)local + 30 + rd16(lh + 26) + rd16(lh + 28), SEEK_SET);
        if (!make_dirs(to, rel)) return "no folder could be made for " + u8(rel);
        const std::wstring dst = to + L"\\" + rel;
        FILE* o = _wfopen(dst.c_str(), L"wb");
        if (!o) return "it could not write " + u8(rel);
        uLong sum = crc32(0L, Z_NULL, 0);
        unsigned long long wrote = 0, left = csize;
        std::string why;
        if (method == 0) {
            if (csize != usize) why = "its files are damaged";
            while (why.empty() && left) {
                const size_t take = (size_t)(left < in.size() ? left : in.size());
                if (fread(in.data(), 1, take, f) != take) { why = "it ends early"; break; }
                if (fwrite(in.data(), 1, take, o) != take) { why = "it could not write " + u8(rel); break; }
                sum = crc32(sum, in.data(), (uInt)take);
                wrote += take;
                left -= take;
            }
        } else {
            z_stream z;
            memset(&z, 0, sizeof z);
            if (inflateInit2(&z, -MAX_WBITS) != Z_OK) why = "out of memory";
            int r = Z_OK;
            while (why.empty() && r != Z_STREAM_END) {
                if (!z.avail_in) {
                    if (!left) { why = "it ends early"; break; }
                    const size_t take = (size_t)(left < in.size() ? left : in.size());
                    if (fread(in.data(), 1, take, f) != take) { why = "it ends early"; break; }
                    left -= take;
                    z.next_in = in.data();
                    z.avail_in = (uInt)take;
                }
                z.next_out = out.data();
                z.avail_out = (uInt)out.size();
                r = inflate(&z, Z_NO_FLUSH);
                if (r != Z_OK && r != Z_STREAM_END && !(r == Z_BUF_ERROR && !z.avail_in)) { why = "its files are damaged"; break; }
                const size_t got = out.size() - z.avail_out;
                if (wrote + got > usize) { why = "its files are damaged"; break; }
                if (got && fwrite(out.data(), 1, got, o) != got) { why = "it could not write " + u8(rel); break; }
                sum = crc32(sum, out.data(), (uInt)got);
                wrote += got;
            }
            inflateEnd(&z);
        }
        if (fclose(o) && why.empty()) why = "it could not write " + u8(rel);
        if (why.empty() && (wrote != usize || sum != crc)) why = "its files are damaged";
        if (!why.empty()) return why;
    }
    return std::string();
}

/* A folder of the unpacked copies, and all in it: only one under mods\.unpacked\, and no link followed. */
void remove_tree(const std::wstring& dir, const std::wstring& within)
{
    if (dir.size() <= within.size() || _wcsnicmp(dir.c_str(), within.c_str(), within.size())) return;
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileExW((dir + L"\\*").c_str(), FindExInfoBasic, &fd, FindExSearchNameMatch, NULL, 0);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (!wcscmp(fd.cFileName, L".") || !wcscmp(fd.cFileName, L"..")) continue;
            const std::wstring p = dir + L"\\" + fd.cFileName;
            if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
                if (fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) RemoveDirectoryW(p.c_str());
                else remove_tree(p, within);
            } else {
                SetFileAttributesW(p.c_str(), FILE_ATTRIBUTE_NORMAL);
                DeleteFileW(p.c_str());
            }
        } while (FindNextFileW(h, &fd));
        FindClose(h);
    }
    RemoveDirectoryW(dir.c_str());
}

/* What a zip is now, for its stamp: its size and when it was written. */
std::string zip_stamp(const std::wstring& zip)
{
    WIN32_FILE_ATTRIBUTE_DATA a;
    if (!GetFileAttributesExW(zip.c_str(), GetFileExInfoStandard, &a)) return std::string();
    char b[64];
    snprintf(b, sizeof b, "%llu %llu", (unsigned long long)a.nFileSizeHigh << 32 | a.nFileSizeLow,
             (unsigned long long)a.ftLastWriteTime.dwHighDateTime << 32 | a.ftLastWriteTime.dwLowDateTime);
    return b;
}

std::string read_small(const std::wstring& p)
{
    std::string s;
    if (FILE* f = _wfopen(p.c_str(), L"rb")) {
        char b[128];
        const size_t n = fread(b, 1, sizeof b, f);
        fclose(f);
        s.assign(b, n);
    }
    return s;
}

/* The zip's unpacked copy, unpacked now if it is new or has changed and unpack says so. */
void zip_mod(const std::wstring& dir, ModInfo* m, int unpack)
{
    const std::wstring zip = dir + L"\\" + m->id, cache_dir = dir + L"\\.unpacked", cache = cache_dir + L"\\" + m->id;
    const std::wstring stamp_file = cache + L".stamp";
    const std::string now = zip_stamp(zip);
    if (!now.empty() && read_small(stamp_file) == now && is_dir(cache)) {
        m->root = cache;
        return;
    }
    if (!unpack) {
        m->error = "not unpacked yet: the launcher unpacks it";
        return;
    }
    if (!CreateDirectoryW(cache_dir.c_str(), NULL) && GetLastError() != ERROR_ALREADY_EXISTS) {
        m->error = "no folder could be made to unpack it in";
        return;
    }
    SetFileAttributesW(cache_dir.c_str(), FILE_ATTRIBUTE_HIDDEN);
    const std::wstring fresh = cache + L".new", old = cache + L".old";
    remove_tree(fresh, cache_dir);
    DeleteFileW(stamp_file.c_str());
    const std::string why = unzip(zip, fresh);
    if (!why.empty()) {
        remove_tree(fresh, cache_dir);
        m->error = "the zip was not unpacked: " + why;
        return;
    }
    remove_tree(old, cache_dir);
    if (is_dir(cache) && !MoveFileW(cache.c_str(), old.c_str())) remove_tree(cache, cache_dir);
    if (!MoveFileW(fresh.c_str(), cache.c_str())) {
        remove_tree(fresh, cache_dir);
        m->error = "the zip was not unpacked: its folder could not be put in place";
        return;
    }
    remove_tree(old, cache_dir);
    if (FILE* s = _wfopen(stamp_file.c_str(), L"wb")) {
        fwrite(now.data(), 1, now.size(), s);
        fclose(s);
    }
    m->root = cache;
}

std::string files_text(int n) { return std::to_string(n) + (n == 1 ? " file" : " files"); }

}  // namespace

std::wstring mods_folder(void)
{
    const char* v = ps3_settings_str("mods", "folder", "GOWA_MODS_DIR", NULL);
    if (v && *v) {
        std::wstring w = wide(v);
        for (wchar_t& c : w) if (c == L'/') c = L'\\';
        while (w.size() > 3 && w.back() == L'\\') w.pop_back();
        const bool absolute = (w.size() >= 2 && w[1] == L':') || (w.size() >= 2 && w[0] == L'\\' && w[1] == L'\\');
        return absolute ? w : settings_dir() + L"\\" + w;
    }
    return settings_dir() + L"\\mods";
}

void mods_scan(ModList* out, int unpack)
{
    out->mods.clear();
    out->dir = mods_folder();
    out->use = ps3_settings_bool("mods", "use", NULL, 1);
    std::vector<std::wstring> ds, fs;
    list_dir(out->dir, &ds, &fs);
    std::vector<ModInfo> found;
    for (const std::wstring& d : ds) {
        if (d.empty() || d[0] == L'.') continue;   /* .unpacked and the like */
        ModInfo m;
        m.id = d;
        m.root = mod_root(out->dir + L"\\" + d, d);
        found.push_back(m);
    }
    for (const std::wstring& f : fs) {
        if (f.size() <= 4 || !same(f.substr(f.size() - 4), L".zip")) continue;
        ModInfo m;
        m.id = f;
        m.zip = 1;
        found.push_back(m);
    }
    /* In the settings' order, then the new ones by name. */
    const std::vector<std::wstring> order = names_of(ps3_settings_str("mods", "order", NULL, ""));
    const std::vector<std::wstring> off = names_of(ps3_settings_str("mods", "off", NULL, ""));
    std::vector<bool> placed(found.size(), false);
    for (const std::wstring& o : order)
        for (size_t i = 0; i < found.size(); i++)
            if (!placed[i] && same(found[i].id, o)) { out->mods.push_back(found[i]); placed[i] = true; break; }
    std::vector<ModInfo> rest;
    for (size_t i = 0; i < found.size(); i++)
        if (!placed[i]) rest.push_back(found[i]);
    auto bare = [](const ModInfo& m) { return upper(m.zip ? m.id.substr(0, m.id.size() - 4) : m.id); };
    std::stable_sort(rest.begin(), rest.end(), [&](const ModInfo& a, const ModInfo& b) { return bare(a) < bare(b); });
    out->mods.insert(out->mods.end(), rest.begin(), rest.end());
    std::unordered_map<std::wstring, size_t> first;   /* a file of the mods that are on: the first one with it */
    for (size_t i = 0; i < out->mods.size(); i++) {
        ModInfo& m = out->mods[i];
        m.on = 1;
        for (const std::wstring& o : off) if (same(m.id, o)) m.on = 0;
        if (m.zip) {
            zip_mod(out->dir, &m, unpack);
            if (!m.root.empty()) m.root = mod_root(m.root, m.id);
        }
        if (m.root.empty()) {
            m.name = u8(m.id.substr(0, m.id.size() - 4));
            continue;
        }
        read_ini(m.root + L"\\mod.ini", &m);
        if (m.name.empty()) m.name = u8(m.zip ? m.id.substr(0, m.id.size() - 4) : m.id);
        layout(&m);
        std::unordered_set<std::wstring> own;
        for (const std::wstring& u : m.usrdirs) {
            std::vector<std::wstring> rels;
            walk(u, std::wstring(), &rels, 0);
            for (const std::wstring& r : rels) {
                if (u == m.root && r.find(L'/') == std::wstring::npos && beside(r)) continue;
                if (!own.insert(r).second) continue;
                if (!m.on) continue;
                auto it = first.find(r);
                if (it == first.end()) first.emplace(r, i);
                else if (!m.shadowed++) m.shadowed_by = out->mods[it->second].id;
            }
        }
        m.files = (int)own.size();
        if (m.error.empty() && m.usrdirs.empty()) {
            if (m.later.empty()) m.error = "it is empty";
            else {
                m.error = "this build does not read its ";
                for (size_t k = 0; k < m.later.size(); k++)
                    m.error += (k ? k + 1 == m.later.size() ? " or " : ", " : "") + m.later[k];
                m.error += " yet";
            }
        }
    }
}

void mods_store(const ModList& l)
{
    std::string order, off;
    for (const ModInfo& m : l.mods) {
        const std::string id = u8(m.id);
        if (order.size() + id.size() + 1 < 1800) order += (order.empty() ? "" : "|") + id;
        if (!m.on && off.size() + id.size() + 1 < 1800) off += (off.empty() ? "" : "|") + id;
    }
    ps3_settings_set("mods", "order", order.c_str());
    ps3_settings_set("mods", "off", off.c_str());
}

std::string mods_dirs(const ModList& l)
{
    std::string s;
    if (!l.use) return s;
    for (const ModInfo& m : l.mods) {
        if (!m.on || !m.error.empty()) continue;
        for (const std::wstring& u : m.usrdirs) s += (s.empty() ? "" : "|") + u8(u);
    }
    return s;
}

std::string mods_summary(const ModList& l)
{
    std::string on, off;
    for (const ModInfo& m : l.mods) {
        std::string one = m.name + (m.version.empty() ? "" : " " + m.version);
        if (!m.error.empty()) one += " (not read: " + m.error + ")";
        else {
            std::string what = files_text(m.files);
            if (m.shadowed) what += ", " + std::to_string(m.shadowed) + " from a mod above";
            if (!m.later.empty()) {
                what += "; not read yet:";
                for (const std::string& k : m.later) what += " " + k;
            }
            one += " (" + what + ")";
        }
        std::string& to = m.on && l.use ? on : off;
        to += (to.empty() ? "" : ", ") + one;
    }
    if (l.mods.empty()) return "none";
    if (!l.use) return "Use mods is off; in the folder: " + off;
    std::string s = on.empty() ? std::string("none on") : on;
    if (!off.empty()) s += "; off: " + off;
    return s;
}
