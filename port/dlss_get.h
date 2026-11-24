/*
 * Ascension-R -- NVIDIA's DLSS DLLs from NVIDIA's own DLSS SDK on GitHub, for the launcher's NVIDIA DLSS scaling and
 * NVIDIA DLSS frame generation (dlss_get.cpp)
 */
#ifndef GOWA_DLSS_GET_H
#define GOWA_DLSS_GET_H

#include <string>

#include "game_prepare.h"

/* The DLLs that are fetched: NVIDIA's DLSS SDK release build, as the game's log and the toast name it. */
extern const char k_dlss_dll_version[];   /* "310.9.16" */

/* Which of them: DLSS's own (Super Resolution, nvngx_dlss.dll), its frame generation's (nvngx_dlssg.dll). */
enum { DLSS_SR = 1, DLSS_FG = 2 };

/* Where the game looks for nvngx_dlss.dll besides the exe's folder: dlss\nvngx_dlss.dll beside the exe. false when the
 * exe's folder is not known. */
bool dlss_dll_path(std::wstring* out);

/* 1 when nvngx_dlss.dll is there, at dlss_dll_path or beside the exe. */
bool dlss_present(void);
/* The same for nvngx_dlssg.dll. */
bool dlssg_present(void);
/* Those of which (DLSS_*) that are not there yet. */
int dlss_missing(int which);
/* Their size in MB, to say before asking. */
int dlss_download_mb(int which);

/* The DLLs of which (DLSS_*) that are not there yet, from NVIDIA's repository into the dlss folder: each one's size and
 * SHA-256 checked against the ones kept here, then NVIDIA's signature on it. "" when done, else why not; nothing is
 * left behind of a file that failed. */
std::string dlss_fetch(GameProgress* p, int which);

#endif
