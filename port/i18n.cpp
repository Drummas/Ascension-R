/*
 * Ascension-R -- the launcher's languages
 *
 * Each translation is a gettext .po file in port/lang, built into the exe (app.rc, RCDATA 301 and on), its msgid the
 * English as the launcher writes it, its msgstr the translation; an empty msgstr is not translated yet. Placeholders
 * (%d, %ls, %hs, ...) stay as they are and in the same order (scripts/lang.py checks). port/lang/launcher.pot lists
 * every text (scripts/lang.py extract).
 *
 * GOWA_LAUNCHER_STRINGS=<file>: every English text looked up is written there once, to find the ones the catalog
 * misses (run with GOWA_LAUNCHER_SHOT to draw every tab).
 */
#include "i18n.h"

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <unordered_map>
#include <unordered_set>

namespace {

struct Lang { const char* code; int res; };
const Lang k_langs[] = { { "id", 301 }, { "zh-s", 302 }, { "zh-t", 303 }, { "ru", 304 }, { "es", 305 },
                         { "pt-br", 306 }, { "de", 307 } };

std::unordered_map<std::string, std::string> s_map;
std::unordered_map<std::wstring, std::wstring> s_wide;   /* TW's translations, by the English */
char s_code[16] = "en";
FILE* s_capture;
std::unordered_set<std::string> s_captured;
int s_capture_init;

std::string utf8(const wchar_t* w)
{
    const int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, NULL, 0, NULL, NULL);
    if (n <= 1) return std::string();
    std::string s((size_t)n - 1, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w, -1, &s[0], n, NULL, NULL);
    return s;
}

std::wstring wide(const std::string& s)
{
    const int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, NULL, 0);
    if (n <= 1) return std::wstring();
    std::wstring w((size_t)n - 1, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, &w[0], n);
    return w;
}

void capture(const std::string& en)
{
    if (!s_capture_init) {
        s_capture_init = 1;
        const char* p = getenv("GOWA_LAUNCHER_STRINGS");
        if (p && *p) s_capture = fopen(p, "ab");
    }
    if (!s_capture || en.empty() || !s_captured.insert(en).second) return;
    /* One per line, its line ends and backslashes escaped as a .po writes them. */
    std::string line;
    for (char c : en) {
        if (c == '\n') line += "\\n";
        else if (c == '\\') line += "\\\\";
        else line += c;
    }
    fprintf(s_capture, "%s\n", line.c_str());
    fflush(s_capture);
}

/* A .po string's contents, between its quotes, unescaped. */
void unquote(const char* p, std::string& out)
{
    const char* q = strchr(p, '"');
    if (!q) return;
    for (q++; *q && *q != '"'; q++) {
        if (*q != '\\' || !q[1]) { out += *q; continue; }
        q++;
        switch (*q) {
        case 'n': out += '\n'; break;
        case 't': out += '\t'; break;
        default: out += *q; break;   /* \" \\ */
        }
    }
}

void parse(const char* data, size_t n)
{
    std::string id, str, *cur = NULL;
    auto flush = [&]() {
        if (!id.empty() && !str.empty()) s_map[id] = str;
        id.clear();
        str.clear();
        cur = NULL;
    };
    const char* p = data;
    const char* end = data + n;
    while (p < end) {
        const char* e = (const char*)memchr(p, '\n', (size_t)(end - p));
        if (!e) e = end;
        std::string line(p, (size_t)(e - p));
        if (!line.empty() && line.back() == '\r') line.pop_back();
        p = e + 1;
        if (!line.compare(0, 6, "msgid ")) {
            flush();
            cur = &id;
            unquote(line.c_str() + 6, id);
        } else if (!line.compare(0, 7, "msgstr ")) {
            cur = &str;
            unquote(line.c_str() + 7, str);
        } else if (!line.empty() && line[0] == '"' && cur) {
            unquote(line.c_str(), *cur);
        }
    }
    flush();
}

}  // namespace

const char* i18n_windows_language(void)
{
    const LANGID l = GetUserDefaultUILanguage();
    const WORD sub = SUBLANGID(l);
    switch (PRIMARYLANGID(l)) {
    case LANG_INDONESIAN: return "id";
    case LANG_CHINESE:    return sub == SUBLANG_CHINESE_SIMPLIFIED || sub == SUBLANG_CHINESE_SINGAPORE ? "zh-s" : "zh-t";
    case LANG_RUSSIAN:    return "ru";
    case LANG_SPANISH:    return "es";
    case LANG_PORTUGUESE: return "pt-br";
    case LANG_GERMAN:     return "de";
    default:              return "en";
    }
}

void i18n_set(const char* code)
{
    if (!code || !*code || !_stricmp(code, "auto")) code = i18n_windows_language();
    if (!_stricmp(code, s_code)) return;
    s_map.clear();
    s_wide.clear();
    snprintf(s_code, sizeof s_code, "en");
    for (const Lang& g : k_langs) {
        if (_stricmp(code, g.code)) continue;
        HRSRC r = FindResourceW(NULL, MAKEINTRESOURCEW(g.res), MAKEINTRESOURCEW(10));   /* RT_RCDATA */
        HGLOBAL h = r ? LoadResource(NULL, r) : NULL;
        const char* data = h ? (const char*)LockResource(h) : NULL;
        const DWORD size = r ? SizeofResource(NULL, r) : 0;
        if (data && size) {
            parse(data, size);
            snprintf(s_code, sizeof s_code, "%s", g.code);
        }
        break;
    }
}

const char* i18n_code(void) { return s_code; }

int i18n_date(int year, int month, int day, wchar_t* out, int n)
{
    /* Each language's own order and month names, from Windows (GetDateFormatEx); English as before: 18 Nov 2026. */
    static const struct { const char* code; const wchar_t* locale; const wchar_t* picture; } k_dates[] = {
        { "en", L"en-GB", L"d MMM yyyy" },
        { "id", L"id-ID", L"d MMM yyyy" },
        { "zh-s", L"zh-CN", L"yyyy'年'M'月'd'日'" },
        { "zh-t", L"zh-TW", L"yyyy'年'M'月'd'日'" },
        { "ru", L"ru-RU", L"d MMM yyyy" },
        { "es", L"es-ES", L"d MMM yyyy" },
        { "pt-br", L"pt-BR", L"d MMM yyyy" },
        { "de", L"de-DE", L"d. MMM yyyy" },
    };
    SYSTEMTIME st = {};
    st.wYear = (WORD)year;
    st.wMonth = (WORD)month;
    st.wDay = (WORD)day;
    const wchar_t* locale = k_dates[0].locale;
    const wchar_t* picture = k_dates[0].picture;
    for (const auto& d : k_dates)
        if (!strcmp(d.code, s_code)) { locale = d.locale; picture = d.picture; }
    return GetDateFormatEx(locale, 0, &st, picture, out, n, NULL) > 0;
}

const char* T(const char* en)
{
    if (!en || !*en) return en;
    capture(en);
    if (s_map.empty()) return en;
    auto it = s_map.find(en);
    return it == s_map.end() ? en : it->second.c_str();
}

const wchar_t* TW(const wchar_t* en)
{
    if (!en || !*en) return en;
    if (!s_capture_init || s_capture) capture(utf8(en));
    if (s_map.empty()) return en;
    /* Only translated texts are kept, so the cache is no bigger than the catalog and what it returned stays valid
     * until the language changes; a text made each frame (a path, a progress line) is looked up each time. */
    auto it = s_wide.find(en);
    if (it != s_wide.end()) return it->second.c_str();
    auto t = s_map.find(utf8(en));
    if (t == s_map.end()) return en;
    return s_wide.emplace(en, wide(t->second)).first->second.c_str();
}
