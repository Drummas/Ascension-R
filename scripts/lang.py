"""The launcher's translations (port/i18n.cpp, port/lang).

  python scripts/lang.py extract            port/lang/launcher.pot: every text the launcher can show, from the sources
  python scripts/lang.py check [code ...]   each port/lang/<code>.po against the catalog: untranslated, stale,
                                            placeholders that differ; exit 1 on a placeholder or escape fault
  python scripts/lang.py update [code ...]  each .po in the catalog's order: new texts added untranslated, stale ones
                                            dropped, translations kept
  python scripts/lang.py missing <file>     texts a GOWA_LAUNCHER_STRINGS capture saw that the catalog lacks

A text's id is its English as the launcher has it at run time (escapes decoded, adjacent literals joined); a
translation keeps every printf placeholder (%d, %ls, %hs, %.1f, %%, ...) in the same order.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG = os.path.join(ROOT, "port", "lang")
SOURCES = ("port/launcher.cpp", "port/game_find.cpp")
CODES = ("id", "zh-s", "zh-t", "ru", "es", "pt-br", "de")

# Calls whose string arguments are never shown: keys, logs, files, comparisons.
NOT_SHOWN = {
    "getenv", "_wgetenv", "strcmp", "_stricmp", "strncmp", "wcscmp", "_wcsicmp", "wcsncmp", "strstr", "wcsstr", "strchr",
    "ps3_settings_ieq", "ps3_settings_str", "ps3_settings_int", "ps3_settings_set", "ps3_settings_get", "opt_find",
    "popt_find", "printf", "fprintf", "puts", "fputs", "OutputDebugStringA", "OutputDebugStringW", "fopen", "_wfopen",
    "LoadLibraryW", "LoadLibraryA", "LoadLibraryExW", "GetProcAddress", "GetModuleHandleW", "CreateFileW",
    "RegOpenKeyExW", "RegQueryValueExW", "RegGetValueW", "sscanf", "swscanf", "env_default", "SetEnvironmentVariableW",
    "SetEnvironmentVariableA", "_putenv", "CreateEventW", "CreateMutexW", "RegisterClassExW", "CreateWindowExW",
    "ShellExecuteW", "wcscat", "wcscpy", "strcat", "strcpy", "wcscat_s", "strcat_s", "lstrcmpiW", "PathAppendW",
    "find_file", "json_str", "json_num", "json_find", "CreateFontFace", "GetFileAttributesW", "DeleteFileW",
    "FindFirstFileW", "CreateDirectoryW", "MoveFileExW", "CopyFileW", "log_line", "kit_log_line", "LOG", "mp_get",
    "ini_get", "ini_set", "http_get", "WinHttpOpen", "WinHttpConnect", "WinHttpOpenRequest", "fwrite", "has_arg",
    "arg_is", "GetEnvironmentVariableW", "GetEnvironmentVariableA", "D2D1CreateFactory", "SetLocaleName",
    "CreateTextFormat", "IID", "__uuidof", "DwmSetWindowAttribute", "PostMessageA", "lstrcmpW", "_wcsnicmp", "_strnicmp",
    "ends_with", "starts_with", "wends_with", "path_join", "wpath_join", "game_link", "ps3_settings_save",
}
NOT_SHOWN |= {"MessageBoxA", "kb_set", "memcmp", "name_is", "CreateWindowExA"}
# Functions whose strings are folder names matched on disk (game_find.cpp's search).
NOT_SHOWN_FUNCS = {"sounds_like_games", "not_worth_it"}
# Shown as they are in every language, or never shown: font names, a signer's name, the window's own name.
KEEP = {"Segoe UI", "Silkscreen", "Bahnschrift", "Segoe Fluent Icons", "Segoe MDL2 Assets", "Apex Compute, Inc.",
        "ASCENSION-R", "Kratos", "GOWA.elf", "Ascension-R %s\n", "English", "Bahasa Indonesia", "Español",
        "Português (Brasil)", "Deutsch", "简体中文", "繁體中文",
        "Русский", "FSR", "DLSS", "SMAA", "SDL3", "HDR", "LOCALAPPDATA", "APPDATA",
        "USERPROFILE", "JanFebMarAprMayJunJulAugSepOctNovDec"}
LIT = re.compile(r'(u8|L)?"((?:[^"\\\n]|\\.)*)"')
# No space flag: the launcher's formats use none, and "5% faster" in a sentence is not one. A stray % in a translation
# is caught by counting them (percents()).
PLACEHOLDER = re.compile(r"%[-+#0-9.*]*(?:hh|h|ll|l|L|z|j|t|I64|I32|I)?[diouxXeEfFgGaAcsSpn%]")


def decode(body, wide):
    """A C literal's text, as the program has it."""
    out = bytearray() if not wide else None
    chars = []
    i = 0
    while i < len(body):
        c = body[i]
        if c != "\\":
            if wide:
                chars.append(c)
            else:
                out += c.encode("utf-8")
            i += 1
            continue
        i += 1
        e = body[i]
        if e == "x":
            j = i + 1
            while j < len(body) and body[j] in "0123456789abcdefABCDEF":
                j += 1
            v = int(body[i + 1:j], 16)
            i = j
            if wide:
                chars.append(chr(v))
            else:
                out.append(v & 255)
            continue
        if e in "uU":
            n = 4 if e == "u" else 8
            v = int(body[i + 1:i + 1 + n], 16)
            i += 1 + n
            if wide:
                chars.append(chr(v))
            else:
                out += chr(v).encode("utf-8")
            continue
        simple = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"', "'": "'", "a": "\a"}
        ch = simple.get(e, e)
        i += 1
        if wide:
            chars.append(ch)
        else:
            out += ch.encode("utf-8")
    return "".join(chars) if wide else out.decode("utf-8", "replace")


def strip_comments(src):
    """The source with comments blanked (same length, same lines), strings kept."""
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '"' or c == "'":
            q = c
            i += 1
            while i < n and src[i] != q and src[i] != "\n":
                i += 2 if src[i] == "\\" else 1
            i += 1
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if src[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def enclosing_function(src, pos):
    """The name of the function a literal is in (the last 'static ... name(' line before it), or ''."""
    last = ""
    for m in re.finditer(r"^static [^\n;=]*?\b(\w+)\(", src[:pos], re.M):
        last = m.group(1)
    return last


def enclosing_call(src, pos):
    """The name of the call whose parentheses hold pos, or ''."""
    depth = 0
    i = pos - 1
    while i >= 0:
        c = src[i]
        if c == '"':
            i -= 1
            while i >= 0 and not (src[i] == '"' and src[i - 1] != "\\"):
                i -= 1
        elif c == ")" or c == "]":
            depth += 1
        elif c == "(" or c == "[":
            if depth == 0:
                if c == "[":
                    return ""
                m = re.search(r"([A-Za-z_][A-Za-z0-9_:]*)\s*$", src[:i])
                return m.group(1) if m else ""
            depth -= 1
        elif c in ";{}" and depth == 0:
            return ""
        i -= 1
    return ""


def shown(text):
    if not text.strip() or text in KEEP:
        return False
    if " " not in text and re.search(r"%l?s", text):    # file name patterns
        return False
    if text.startswith("*.") or "\t" in text:            # file filters, test fixtures
        return False
    bare = PLACEHOLDER.sub("", text)
    if not re.search(r"[A-Za-z]{2,}", bare):
        return False
    if re.fullmatch(r"[a-z0-9_.\-/:+]+", text):        # keys, values, file names
        return False
    if re.fullmatch(r"[A-Z0-9_]+", text) and ("_" in text or re.search(r"\d{3}", text)):   # constants, title IDs
        return False
    if re.search(r"(^|\s)--[a-z]", text):              # command lines
        return False
    if re.search(r"\\[A-Za-z_]|[A-Za-z]:/|\.(exe|dll|py|bin|json|ini|log|txt|pdb)\b|https?://|--[a-z]", text) and " " not in text:
        return False
    if re.search(r"https?://", text):
        return False
    if text.startswith("[") and "]" in text[:20]:      # log lines
        return False
    if chr(13) in text:                                      # a file's contents (the mods folder's readme)
        return False
    return True


def extract(out=None):
    seen, ctx = {}, {}
    order = []
    # The keyboard keys' default bindings (k_kb's third column) are key names as the settings file has them, shown as
    # they are; the second column is the button's name, translated.
    launcher = open(os.path.join(ROOT, "port", "launcher.cpp"), encoding="utf-8").read()
    rows = re.findall(r'\{\s*"[a-z0-9_]+",\s*"([^"]+)",\s*"([^"]*)"\s*\}', launcher)
    labels = {r[0] for r in rows}
    keys = {r[1] for r in rows}
    for rel in SOURCES:
        src = strip_comments(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        i = 0
        while True:
            m = LIT.search(src, i)
            if not m:
                break
            # A '...' character literal holding a quote is not a string.
            if m.start() > 0 and src[m.start() - 1] == "'":
                i = m.end()
                continue
            start = m.start()
            wide = m.group(1) == "L"
            parts = [decode(m.group(2), wide)]
            end = m.end()
            while True:
                n = re.compile(r'\s*(u8|L)?"((?:[^"\\\n]|\\.)*)"').match(src, end)
                if not n:
                    break
                parts.append(decode(n.group(2), wide or n.group(1) == "L"))
                end = n.end()
            i = end
            text = "".join(parts)
            if src.startswith("#include", src.rfind("\n", 0, start) + 1):
                continue
            call = enclosing_call(src, start)
            if call in NOT_SHOWN or not shown(text) or enclosing_function(src, start) in NOT_SHOWN_FUNCS:
                continue
            if text in keys and text not in labels:
                continue
            line = src.count("\n", 0, start) + 1
            if text not in seen:
                seen[text] = []
                ctx[text] = []
                order.append(text)
            seen[text].append("%s:%d" % (os.path.basename(rel), line))
            # Where it shows, for the translator: a button's, a list's or a format's text.
            if call and call not in ctx[text] and call not in ("W", "TW", "T", "UP"):
                ctx[text].append(call)
    # The game patches' names: the game module's table (scripts/title_patches.json), shown as the Game patches rows.
    import json
    for p in json.load(open(os.path.join(ROOT, "scripts", "title_patches.json"), encoding="utf-8"))["patches"]:
        name = p.get("name") if isinstance(p, dict) else None
        if name and name not in seen:
            seen[name] = ["title_patches.json"]
            order.append(name)
    # The Kit build's stages, as the launcher shows them while the game's code is built (gowa.py PROGRESS.phase).
    gowa = open(os.path.join(ROOT, "scripts", "gowa.py"), encoding="utf-8").read()
    stages = re.findall(r'PROGRESS\.phase\([^,]+,\s*"([^"]+)"', gowa)
    stages += re.findall(r'what = "([^"]+)" if not pre else "([^"]+)"', gowa)[0] if 'what = "' in gowa else []
    stages += re.findall(r'"Translating the SPU programs" if not pre else "([^"]+)"', gowa)
    for name in stages:
        if name not in seen:
            seen[name] = ["gowa.py"]
            ctx[name] = ["Kit build stage"]
            order.append(name)
    with open(out or os.path.join(LANG, "launcher.pot"), "w", encoding="utf-8", newline="\n") as f:
        f.write('# Ascension-R launcher: every text it can show (scripts/lang.py extract)\n')
        f.write('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n')
        for t in order:
            if ctx.get(t):
                f.write("#. %s\n" % ", ".join(ctx[t][:3]))
            f.write("#: %s\n" % " ".join(seen[t][:4]))
            f.write("msgid %s\nmsgstr \"\"\n\n" % quote(t))
    words = sum(len(t.split()) for t in order)
    print("launcher.pot: %d texts, %d words" % (len(order), words))


def quote(t):
    return '"' + t.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r") + '"'


def unquote(s):
    s = s.strip()
    assert s.startswith('"') and s.endswith('"'), s
    body = s[1:-1]
    out, i = [], 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            e = body[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(e, e))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def read_po(path):
    """[(comments, msgid, msgstr)] in file order, the header (msgid "") first."""
    entries = []
    comments, msgid, msgstr, cur = [], None, None, None
    lines = open(path, encoding="utf-8", newline="").read().replace("\r\n", "\n").split("\n")
    for line in lines + [""]:
        if line.startswith("msgid "):
            if msgid is not None:
                entries.append((comments, msgid, msgstr or ""))
                comments = []
            msgid, msgstr, cur = unquote(line[6:]), None, "id"
        elif line.startswith("msgstr "):
            msgstr, cur = unquote(line[7:]), "str"
        elif line.startswith('"') and cur:
            if cur == "id":
                msgid += unquote(line)
            else:
                msgstr += unquote(line)
        else:
            if msgid is not None and cur == "str":
                entries.append((comments, msgid, msgstr or ""))
                comments, msgid, msgstr, cur = [], None, None, None
            if line.startswith("#"):
                comments.append(line)
    return entries


def placeholders(t):
    return PLACEHOLDER.findall(t)


def fault(en, tr):
    """Why a translation would break the launcher, or None: other placeholders, or another count of % signs (a format
    with a stray % misreads its arguments)."""
    if placeholders(en) != placeholders(tr):
        return "placeholders differ"
    if en.count("%") != tr.count("%"):
        return "another number of % signs (a literal percent in a format is %%)"
    return None


def check(codes):
    pot = [e for e in read_po(os.path.join(LANG, "launcher.pot")) if e[1]]
    ids = [e[1] for e in pot]
    bad = 0
    for code in codes:
        path = os.path.join(LANG, code + ".po")
        if not os.path.exists(path):
            print("%s: no file" % code)
            continue
        po = {e[1]: e[2] for e in read_po(path) if e[1]}
        done = [i for i in ids if po.get(i)]
        stale = [i for i in po if i not in set(ids) and po[i]]
        faults = []
        for i in done:
            if fault(i, po[i]):
                faults.append((i, po[i]))
            elif i.count("\n") != po[i].count("\n") and "\n" in i:
                pass   # line breaks may differ in a translation
        print("%-6s %4d of %d translated, %d stale, %d placeholder faults" % (code, len(done), len(ids), len(stale), len(faults)))
        for i, t in faults[:20]:
            print("   placeholders differ:\n     en: %r\n     %s: %r" % (i, code, t))
        bad += len(faults)
    return 1 if bad else 0


def update(codes):
    pot = [e for e in read_po(os.path.join(LANG, "launcher.pot")) if e[1]]
    for code in codes:
        path = os.path.join(LANG, code + ".po")
        old = read_po(path) if os.path.exists(path) else []
        header = next((e for e in old if not e[1]), None)
        tr = {e[1]: e[2] for e in old if e[1]}
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            if header:
                f.write("\n".join(c for c in header[0]) + ("\n" if header[0] else ""))
                f.write('msgid ""\nmsgstr %s\n\n' % quote(header[2]))
            for comments, msgid, _ in pot:
                f.write("\n".join(comments) + ("\n" if comments else ""))
                f.write("msgid %s\nmsgstr %s\n\n" % (quote(msgid), quote(tr.get(msgid, ""))))
        print("%s: %d texts" % (code, len(pot)))


def missing(path):
    ids = {e[1] for e in read_po(os.path.join(LANG, "launcher.pot"))}
    n = 0
    for raw in open(path, encoding="utf-8", errors="replace"):
        t = raw.rstrip("\n").replace("\\n", "\n").replace("\\\\", "\\")
        if t and t not in ids and shown(t):
            print(repr(t))
            n += 1
    print("%d not in the catalog" % n)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "extract":
        extract()
        return 0
    if cmd == "check":
        return check(args or CODES)
    if cmd == "update":
        update(args or CODES)
        return 0
    if cmd == "missing" and args:
        missing(args[0])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
