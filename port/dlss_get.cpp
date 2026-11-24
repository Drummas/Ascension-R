/*
 * Ascension-R -- NVIDIA's DLSS DLLs from NVIDIA's own DLSS SDK on GitHub, for the launcher's NVIDIA DLSS scaling and
 * NVIDIA DLSS frame generation (dlss_get.h)
 *
 * Only when the player says so (the launcher asks first). Two files of the release build of NVIDIA's DLSS SDK
 * 310.9.16, from github.com/NVIDIA/DLSS at the commit of that tag, through game_download: nvngx_dlss.dll for the
 * scaling, nvngx_dlssg.dll for frame generation (the same file NVIDIA's Streamline SDK 2.14.16 carries, which runs it).
 * Each is checked against the size and SHA-256 kept here and then NVIDIA's Authenticode signature, and put in dlss\
 * beside the exe, where the game looks for them (rsx_dlss.cpp, rsx_sl.cpp). The DLLs are NVIDIA's, under the NVIDIA RTX
 * SDKs license: the project keeps nothing of them and fetches them only for a player who asks, only from NVIDIA's own
 * repository. The build takes the SDK's headers and library from the same commit (ps3recomp's CMakeLists.txt), so the
 * two match.
 */
#include "dlss_get.h"
#include "anr_get.h"      /* anr_signer: Authenticode, offline */
#include "game_find.h"    /* game_file_sha256 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

const char k_dlss_dll_version[] = "310.9.16";

#define DLSS_SDK_URL L"https://raw.githubusercontent.com/NVIDIA/DLSS/9981c6350dc58c0ce21f024fd65e31e851c31689/lib/Windows_x86_64/rel/"

static const struct {
    int which;
    const wchar_t* name;
    const wchar_t* url;
    long long size;
    const char* sha256;
} k_dlls[] = {
    { DLSS_SR, L"nvngx_dlss.dll", DLSS_SDK_URL L"nvngx_dlss.dll", 58956912,
      "d00b5b0ab29c3ca101b70c3a5ecb3a01b7ef33766a3383a28a18623083e6123e" },
    { DLSS_FG, L"nvngx_dlssg.dll", DLSS_SDK_URL L"nvngx_dlssg.dll", 7506544,
      "8d59d49b36410dd6b62fef2503a5871d347415bd85d943fa0848563a95dd50c7" },
};

static bool exe_dir(std::wstring* out)
{
    wchar_t exe[MAX_PATH];
    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
    if (!n || n >= MAX_PATH) return false;
    while (n && exe[n - 1] != L'\\') n--;
    if (!n) return false;
    *out = std::wstring(exe, n);   /* with its backslash */
    return true;
}

bool dlss_dll_path(std::wstring* out)
{
    std::wstring dir;
    if (!exe_dir(&dir)) return false;
    *out = dir + L"dlss\\nvngx_dlss.dll";
    return true;
}

/* In dlss\ or beside the exe. */
static bool dll_present(const wchar_t* name)
{
    std::wstring dir;
    if (!exe_dir(&dir)) return false;
    return GetFileAttributesW((dir + L"dlss\\" + name).c_str()) != INVALID_FILE_ATTRIBUTES ||
           GetFileAttributesW((dir + name).c_str()) != INVALID_FILE_ATTRIBUTES;
}

bool dlss_present(void) { return dll_present(L"nvngx_dlss.dll"); }
bool dlssg_present(void) { return dll_present(L"nvngx_dlssg.dll"); }

int dlss_missing(int which)
{
    int m = 0;
    for (const auto& d : k_dlls)
        if ((which & d.which) && !dll_present(d.name)) m |= d.which;
    return m;
}

int dlss_download_mb(int which)
{
    long long n = 0;
    for (const auto& d : k_dlls)
        if (which & d.which) n += d.size;
    return (int)((n + (1 << 20) - 1) >> 20);
}

static long long file_size(const std::wstring& path)
{
    WIN32_FILE_ATTRIBUTE_DATA a;
    if (!GetFileAttributesExW(path.c_str(), GetFileExInfoStandard, &a)) return -1;
    return ((long long)a.nFileSizeHigh << 32) | a.nFileSizeLow;
}

std::string dlss_fetch(GameProgress* p, int which)
{
    std::wstring dir;
    if (!exe_dir(&dir)) return "the game's folder is not known";
    dir += L"dlss";
    if (!CreateDirectoryW(dir.c_str(), NULL) && GetLastError() != ERROR_ALREADY_EXISTS)
        return "no dlss folder could be made beside the game";
    for (const auto& d : k_dlls) {
        if (!(which & d.which) || dll_present(d.name)) continue;
        const std::wstring dll = dir + L"\\" + d.name;
        const std::wstring part = dll + L".download";
        char name[64];
        WideCharToMultiByte(CP_UTF8, 0, d.name, -1, name, sizeof name, NULL, NULL);
        DeleteFileW(part.c_str());
        wchar_t err[400] = L"";
        if (!game_download(d.url, part.c_str(), L"NVIDIA DLSS", p, err, 400)) {
            DeleteFileW(part.c_str());
            char e[800];
            WideCharToMultiByte(CP_UTF8, 0, err, -1, e, sizeof e, NULL, NULL);
            return e[0] ? std::string(e) : std::string("the download of ") + name + " failed";
        }
        char hex[65] = "";
        if (file_size(part) != d.size || !game_file_sha256(part.c_str(), hex) || _stricmp(hex, d.sha256)) {
            DeleteFileW(part.c_str());
            return "the download is not NVIDIA's DLSS " + std::string(k_dlss_dll_version) + " " + name +
                   " (its SHA-256 differs)";
        }
        std::wstring who;
        if (!anr_signer(part, &who) || who != L"NVIDIA Corporation") {
            DeleteFileW(part.c_str());
            return std::string(name) + " is not signed by NVIDIA Corporation, so it was taken out again";
        }
        if (!MoveFileExW(part.c_str(), dll.c_str(), MOVEFILE_REPLACE_EXISTING)) {
            DeleteFileW(part.c_str());
            return std::string(name) + " could not be put in the dlss folder (is the game running?)";
        }
    }
    return std::string();
}
