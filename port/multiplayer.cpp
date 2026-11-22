/*
 * Ascension-R -- multiplayer from the launcher's settings (docs/notes/2026-11-22-multiplayer-phase5.md).
 *
 * [online]
 *   mode       off | host | join
 *   name       the player's online id: 3-16 letters, digits, - and _, starting with a letter
 *   server     join: the host's address (a name or an IPv4 address)
 *   relay      off | on: the game's datagrams always through the host's relay
 *   port       the UDP port other players reach this game at (3658)
 *   game_mode  host: every Quick Play match in this game mode (empty: as the players' searches suggest)
 *   players    host: Quick Play waits for this many players and puts them all in one world
 *
 * gowa_online_start runs scripts\mp_node.py with the Kit's Python (kit\ beside the program; in a build tree, scripts\
 * beside build\ with the .venv's Python or one on the PATH; GOWA_PYTHON names another) in a job that ends with this
 * process, and waits for the node's game.env: the variables the runtime's network and NP read, put into this
 * environment before anything reads them. host leaves the node running: the matchmaker and the signaling server for
 * this game and the players who join it. The node's folder is online\ beside the settings: tss.bin, np_tus\ (the
 * multiplayer profile), node.log.
 */
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iphlpapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include "ps3emu/ps3_settings.h"
#pragma comment(lib, "iphlpapi.lib")

namespace {

std::wstring wide(const char* s)
{
    if (!s || !*s) return std::wstring();
    const int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0);
    if (n <= 1) return std::wstring();
    std::wstring w((size_t)n - 1, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s, -1, &w[0], n);
    return w;
}

bool is_file(const std::wstring& p)
{
    const DWORD a = GetFileAttributesW(p.c_str());
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

std::wstring full(const std::wstring& p)
{
    wchar_t b[MAX_PATH * 2];
    const DWORD k = GetFullPathNameW(p.c_str(), MAX_PATH * 2, b, NULL);
    return k && k < MAX_PATH * 2 ? std::wstring(b) : p;
}

std::wstring exe_dir(void)
{
    wchar_t exe[MAX_PATH];
    const DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
    if (!n || n >= MAX_PATH) return L".";
    if (wchar_t* e = wcsrchr(exe, L'\\')) *e = 0;
    return exe;
}

/* The settings file's folder, else the program's (mods.cpp's rule). */
std::wstring settings_dir(void)
{
    std::wstring here = wide(ps3_settings_path());
    for (wchar_t& c : here) if (c == L'/') c = L'\\';
    const size_t s = here.find_last_of(L'\\');
    return s != std::wstring::npos ? here.substr(0, s) : exe_dir();
}

/* The Python and mp_node.py to run: the Kit's, else a build tree's (mods.cpp's find_packer rule). */
bool find_node(std::wstring* py, std::wstring* script)
{
    const std::wstring here = exe_dir();
    if (is_file(here + L"\\kit\\python\\python.exe") && is_file(here + L"\\kit\\scripts\\mp_node.py")) {
        *py = here + L"\\kit\\python\\python.exe";
        *script = here + L"\\kit\\scripts\\mp_node.py";
    } else if (is_file(here + L"\\..\\scripts\\mp_node.py")) {
        *script = full(here + L"\\..\\scripts\\mp_node.py");
        if (is_file(here + L"\\..\\..\\.venv\\Scripts\\python.exe")) *py = full(here + L"\\..\\..\\.venv\\Scripts\\python.exe");
        else {
            wchar_t found[MAX_PATH];
            if (SearchPathW(NULL, L"python.exe", NULL, MAX_PATH, found, NULL)) *py = found;
        }
    }
    if (const wchar_t* e = _wgetenv(L"GOWA_PYTHON")) if (*e) *py = e;
    return !py->empty() && !script->empty() && is_file(*py) && is_file(*script);
}

const char* setting(const char* key) { return ps3_settings_str("online", key, NULL, ""); }

/* A host's address as the player typed it: a name or an IPv4 address, nothing that could end the command line. */
bool address_ok(const char* s)
{
    size_t n = 0;
    for (; s[n]; n++) {
        const char c = s[n];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '-'))
            return false;
    }
    return n > 0 && n <= 253;
}

/* A number setting, "" when it is not one (then left out). */
std::wstring number(const char* key, long lo, long hi)
{
    const char* v = setting(key);
    if (!*v) return std::wstring();
    char* end = NULL;
    const long k = strtol(v, &end, 10);
    if (*end || k < lo || k > hi) return std::wstring();
    return std::to_wstring(k);
}

std::string read_small(const std::wstring& path, size_t cap)
{
    std::string s;
    HANDLE h = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL,
                           OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return s;
    char buf[4096];
    DWORD got = 0;
    while (s.size() < cap && ReadFile(h, buf, sizeof buf, &got, NULL) && got) s.append(buf, got);
    CloseHandle(h);
    return s;
}

/* The last line of a text that is not empty: a Python's own complaint, when the node could not say why. */
std::string last_line(const std::string& s)
{
    size_t end = s.find_last_not_of("\r\n \t");
    if (end == std::string::npos) return std::string();
    const size_t start = s.find_last_of('\n', end);
    return s.substr(start == std::string::npos ? 0 : start + 1, end + 1 - (start == std::string::npos ? 0 : start + 1));
}

int s_state;          /* 0 not started (or it failed: the launcher may try again), 1 started or off */
HANDLE s_job;         /* the node's: never closed, so the node ends with this process */
char s_why[300];

int fail(char* why, size_t n, const char* fmt, const char* a = "")
{
    snprintf(s_why, sizeof s_why, fmt, a);
    if (why && n) snprintf(why, n, "%s", s_why);
    fprintf(stderr, "[online] %s\n", s_why);
    return 0;
}

}  // namespace

/* 0 off, 1 host, 2 join. */
extern "C" int gowa_online_mode(void)
{
    const char* m = setting("mode");
    return !_stricmp(m, "host") ? 1 : !_stricmp(m, "join") ? 2 : 0;
}

/* The runtime's rule for an online id (np_psnr.c), taken as it is: 1 if name is one. */
extern "C" int gowa_online_name_ok(const char* name)
{
    size_t n = 0;
    if (!name) return 0;
    for (; name[n]; n++) {
        const char c = name[n];
        const int letter = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
        if (!letter && !(c >= '0' && c <= '9') && c != '-' && c != '_') return 0;
        if (n == 0 && !letter) return 0;
    }
    return n >= 3 && n <= 16;
}

/* A host's address as the launcher takes it: a name or an IPv4 address. */
extern "C" int gowa_online_address_ok(const char* s) { return s && address_ok(s); }

/* What stops multiplayer from starting with these settings, or NULL: the launcher says it before Play (a toast, so
 * short). */
extern "C" const char* gowa_online_problem(void)
{
    const int mode = gowa_online_mode();
    if (!mode) return NULL;
    if (!gowa_online_name_ok(setting("name"))) return "Multiplayer: set your online ID first";
    if (mode == 2 && !address_ok(setting("server"))) return "Multiplayer: set the host's address first";
    std::wstring py, script;
    if (!find_node(&py, &script)) return "Multiplayer needs the Kit's Python";
    return NULL;
}

/* This PC's IPv4 addresses that other players could reach, each with its network's name ("192.168.1.20 (Wi-Fi)"),
 * ", " between them; "" when there is none. Loopback and self-assigned (169.254) ones are left out. */
extern "C" void gowa_online_lan(char* out, size_t n)
{
    if (!out || !n) return;
    out[0] = 0;
    ULONG size = 16384;
    std::string buf;
    DWORD r = ERROR_BUFFER_OVERFLOW;
    for (int tries = 0; tries < 3 && r == ERROR_BUFFER_OVERFLOW; tries++) {
        buf.resize(size);
        r = GetAdaptersAddresses(AF_INET, GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER,
                                 NULL, reinterpret_cast<IP_ADAPTER_ADDRESSES*>(&buf[0]), &size);
    }
    if (r != NO_ERROR) return;
    std::string list;
    int count = 0;
    for (const IP_ADAPTER_ADDRESSES* a = reinterpret_cast<const IP_ADAPTER_ADDRESSES*>(buf.data()); a && count < 4;
         a = a->Next) {
        if (a->OperStatus != IfOperStatusUp || a->IfType == IF_TYPE_SOFTWARE_LOOPBACK) continue;
        for (const IP_ADAPTER_UNICAST_ADDRESS* u = a->FirstUnicastAddress; u && count < 4; u = u->Next) {
            const sockaddr* sa = u->Address.lpSockaddr;
            if (!sa || sa->sa_family != AF_INET) continue;
            const unsigned char* b = reinterpret_cast<const unsigned char*>(
                &reinterpret_cast<const sockaddr_in*>(sa)->sin_addr);
            if (b[0] == 127 || (b[0] == 169 && b[1] == 254)) continue;
            char ip[64], name[96] = "";
            snprintf(ip, sizeof ip, "%u.%u.%u.%u", b[0], b[1], b[2], b[3]);
            if (a->FriendlyName)
                WideCharToMultiByte(CP_UTF8, 0, a->FriendlyName, -1, name, (int)sizeof name, NULL, NULL);
            if (!list.empty()) list += ", ";
            list += ip;
            if (name[0]) list += std::string(" (") + name + ")";
            count++;
        }
    }
    snprintf(out, n, "%s", list.c_str());
}

/* Multiplayer as the settings say: the node started and its variables in this environment. 1 when that is done or
 * multiplayer is off; 0 and why when it could not be (the game then plays without it). Once a process. */
extern "C" int gowa_online_start(char* why, size_t n)
{
    if (s_state == 1) return 1;
    const int mode = gowa_online_mode();
    if (!mode) {
        s_state = 1;
        return 1;
    }
    if (const char* p = gowa_online_problem()) return fail(why, n, "%s", p);
    const char* elf = ps3_settings_str("paths", "elf", NULL, NULL);
    if (!elf || !*elf || !is_file(wide(elf))) return fail(why, n, "Multiplayer: no GOWA.elf where the settings say");
    std::wstring py, script;
    find_node(&py, &script);
    const std::wstring dir = settings_dir() + L"\\online";
    CreateDirectoryW(dir.c_str(), NULL);
    const std::wstring env_file = dir + L"\\game.env", err_file = dir + L"\\node.error", out_file = dir + L"\\node.out";
    DeleteFileW(env_file.c_str());
    DeleteFileW(err_file.c_str());

    std::wstring cmd = L"\"" + py + L"\" -E -s -B -X utf8 \"" + script + L"\" " + (mode == 1 ? L"host" : L"join") +
                       L" --name " + wide(setting("name")) + L" --elf \"" + wide(elf) + L"\" --dir \"" + dir + L"\"";
    if (mode == 2) cmd += L" --server " + wide(setting("server"));
    if (ps3_settings_bool("online", "relay", NULL, 0)) cmd += L" --relay";
    const std::wstring port = number("port", 1024, 65535);
    if (!port.empty()) cmd += L" --p2p-port " + port;
    if (mode == 1) {
        const std::wstring gm = number("game_mode", 1, 255), players = number("players", 1, 16);
        if (!gm.empty()) cmd += L" --mode " + gm;
        if (!players.empty()) cmd += L" --players " + players;
    }

    SECURITY_ATTRIBUTES sa = { sizeof sa, NULL, TRUE };
    HANDLE out = CreateFileW(out_file.c_str(), GENERIC_WRITE, FILE_SHARE_READ, &sa, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL,
                             NULL);
    HANDLE job = CreateJobObjectW(NULL, NULL);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION li = {};
    li.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!job || !SetInformationJobObject(job, JobObjectExtendedLimitInformation, &li, sizeof li)) {
        if (job) CloseHandle(job);
        if (out != INVALID_HANDLE_VALUE) CloseHandle(out);
        return fail(why, n, "Multiplayer: the node could not be started");
    }
    STARTUPINFOW si = {};
    si.cb = sizeof si;
    if (out != INVALID_HANDLE_VALUE) {
        si.dwFlags = STARTF_USESTDHANDLES;
        si.hStdOutput = si.hStdError = out;
        si.hStdInput = NULL;
    }
    PROCESS_INFORMATION pi = {};
    BOOL ok = CreateProcessW(py.c_str(), &cmd[0], NULL, NULL, out != INVALID_HANDLE_VALUE,
                             CREATE_NO_WINDOW | CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT, NULL, dir.c_str(), &si, &pi);
    if (out != INVALID_HANDLE_VALUE) CloseHandle(out);
    if (ok && !AssignProcessToJobObject(job, pi.hProcess)) {
        TerminateProcess(pi.hProcess, 1);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        ok = FALSE;
    }
    if (!ok) {
        CloseHandle(job);
        return fail(why, n, "Multiplayer: the node could not be started");
    }
    ResumeThread(pi.hThread);
    CloseHandle(pi.hThread);

    /* Its game.env, or its end: about a second (Python, the TSS); 30 at most. */
    std::string env;
    for (int t = 0; t < 600; t++) {
        if (is_file(env_file)) {
            env = read_small(env_file, 1 << 16);
            if (!env.empty()) break;
        }
        if (WaitForSingleObject(pi.hProcess, 50) == WAIT_OBJECT_0 && !is_file(env_file)) break;
    }
    if (env.empty()) {
        std::string w = last_line(read_small(err_file, 4096));
        if (w.empty()) w = last_line(read_small(out_file, 1 << 16));
        TerminateJobObject(job, 1);
        CloseHandle(job);
        CloseHandle(pi.hProcess);
        return fail(why, n, "Multiplayer: %s", w.empty() ? "the node gave no answer (online\\node.log)" : w.c_str());
    }
    CloseHandle(pi.hProcess);
    s_job = job;   /* kept: the node ends with this process */

    size_t at = 0;
    int vars = 0;
    while (at < env.size()) {
        size_t end = env.find('\n', at);
        if (end == std::string::npos) end = env.size();
        std::string line = env.substr(at, end - at);
        at = end + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const size_t eq = line.find('=');
        if (eq == std::string::npos || !eq) continue;
        _putenv_s(line.substr(0, eq).c_str(), line.substr(eq + 1).c_str());   /* "" takes it away */
        vars++;
    }
    printf("[online] %s as %s%s%s: %d variables from %ls\n", mode == 1 ? "hosting" : "joining", setting("name"),
           mode == 2 ? " " : "", mode == 2 ? setting("server") : "", vars, env_file.c_str());
    s_state = 1;
    return 1;
}
