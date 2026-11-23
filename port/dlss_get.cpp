/*
 * Ascension-R -- NVIDIA's DLSS DLL from NVIDIA's own DLSS SDK on GitHub, for the launcher's NVIDIA DLSS scaling
 * (dlss_get.h)
 *
 * Only when the player says so (the launcher asks first). One file: nvngx_dlss.dll, the release build of NVIDIA's DLSS
 * SDK 310.9.16, from github.com/NVIDIA/DLSS at the commit of that tag, through game_download; checked against the
 * size and SHA-256 kept here and then NVIDIA's Authenticode signature, and put in dlss\ beside the exe, where the game
 * looks for it (rsx_dlss.cpp). The DLL is NVIDIA's, under the NVIDIA RTX SDKs license: the project keeps nothing of it
 * and fetches it only for a player who asks, only from NVIDIA's own repository. The build takes the SDK's headers and
 * library from the same commit (ps3recomp's CMakeLists.txt), so the two match.
 */
#include "dlss_get.h"
#include "anr_get.h"      /* anr_signer: Authenticode, offline */
#include "game_find.h"    /* game_file_sha256 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

const char k_dlss_dll_version[] = "310.9.16";

static const wchar_t k_dlss_url[] =
    L"https://raw.githubusercontent.com/NVIDIA/DLSS/9981c6350dc58c0ce21f024fd65e31e851c31689/lib/Windows_x86_64/rel/"
    L"nvngx_dlss.dll";
static const long long k_dlss_size = 58956912;
static const char k_dlss_sha256[] = "d00b5b0ab29c3ca101b70c3a5ecb3a01b7ef33766a3383a28a18623083e6123e";

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

bool dlss_present(void)
{
    std::wstring dll, dir;
    if (dlss_dll_path(&dll) && GetFileAttributesW(dll.c_str()) != INVALID_FILE_ATTRIBUTES) return true;
    return exe_dir(&dir) && GetFileAttributesW((dir + L"nvngx_dlss.dll").c_str()) != INVALID_FILE_ATTRIBUTES;
}

static long long file_size(const std::wstring& path)
{
    WIN32_FILE_ATTRIBUTE_DATA a;
    if (!GetFileAttributesExW(path.c_str(), GetFileExInfoStandard, &a)) return -1;
    return ((long long)a.nFileSizeHigh << 32) | a.nFileSizeLow;
}

std::string dlss_fetch(GameProgress* p)
{
    std::wstring dll;
    if (!dlss_dll_path(&dll)) return "the game's folder is not known";
    const std::wstring dir = dll.substr(0, dll.find_last_of(L'\\'));
    const std::wstring part = dll + L".download";
    if (!CreateDirectoryW(dir.c_str(), NULL) && GetLastError() != ERROR_ALREADY_EXISTS)
        return "no dlss folder could be made beside the game";
    DeleteFileW(part.c_str());
    wchar_t err[400] = L"";
    if (!game_download(k_dlss_url, part.c_str(), L"NVIDIA DLSS", p, err, 400)) {
        DeleteFileW(part.c_str());
        char e[800];
        WideCharToMultiByte(CP_UTF8, 0, err, -1, e, sizeof e, NULL, NULL);
        return e[0] ? std::string(e) : std::string("the download failed");
    }
    char hex[65] = "";
    if (file_size(part) != k_dlss_size || !game_file_sha256(part.c_str(), hex) || _stricmp(hex, k_dlss_sha256)) {
        DeleteFileW(part.c_str());
        return "the download is not NVIDIA's DLSS " + std::string(k_dlss_dll_version) + " DLL (its SHA-256 differs)";
    }
    std::wstring who;
    if (!anr_signer(part, &who) || who != L"NVIDIA Corporation") {
        DeleteFileW(part.c_str());
        return "the DLL is not signed by NVIDIA Corporation, so it was taken out again";
    }
    if (!MoveFileExW(part.c_str(), dll.c_str(), MOVEFILE_REPLACE_EXISTING)) {
        DeleteFileW(part.c_str());
        return "the DLL could not be put in the dlss folder (is the game running?)";
    }
    return std::string();
}
