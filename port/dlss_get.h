/*
 * Ascension-R -- NVIDIA's DLSS DLL from NVIDIA's own DLSS SDK on GitHub, for the launcher's NVIDIA DLSS scaling
 * (dlss_get.cpp)
 */
#ifndef GOWA_DLSS_GET_H
#define GOWA_DLSS_GET_H

#include <string>

#include "game_prepare.h"

/* The DLL that is fetched: NVIDIA's DLSS SDK release build, as the game's log and the toast name it. */
extern const char k_dlss_dll_version[];   /* "310.9.16" */

/* Where the game looks for it besides the exe's folder: dlss\nvngx_dlss.dll beside the exe. false when the exe's
 * folder is not known. */
bool dlss_dll_path(std::wstring* out);

/* 1 when it is there, at dlss_dll_path or beside the exe. */
bool dlss_present(void);

/* nvngx_dlss.dll from NVIDIA's repository into dlss_dll_path: its size and SHA-256 checked against the ones kept
 * here, then NVIDIA's signature on it. "" when done, else why not; nothing is left behind on a failure. */
std::string dlss_fetch(GameProgress* p);

#endif
