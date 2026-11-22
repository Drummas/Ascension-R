/*
 * Ascension-R -- ANR FG from Apex Compute's own releases, for the launcher's Frame generation choice (anr_get.cpp)
 */
#ifndef GOWA_ANR_GET_H
#define GOWA_ANR_GET_H

#include <string>

#include "game_prepare.h"

/* The newest release of github.com/apex-compute/ANR and the zip of it that is taken: the addon zip (the folder with
 * nvngx_dlssg.dll and little else), else the full one. */
struct AnrRelease {
    std::string tag;        /* "FG-V.B20" */
    std::string name;       /* "anr-fg-V.B20-addon.zip" */
    std::wstring url;       /* its download address, on github.com/apex-compute/ANR/releases/download/ */
    long long size = 0;
    std::string sha256;     /* lower-case hex, as GitHub gives it for the file or the release's SHA256SUMS.txt */
};

/* Asks api.github.com for the newest release. "" when it has an ANR FG zip with a SHA-256, else why not. */
std::string anr_latest(AnrRelease* r);

/* The release's zip into file (game_download), checked against its SHA-256. "" when done, else why not. */
std::string anr_fetch(const AnrRelease& r, const std::wstring& file, GameProgress* p);

/* Who signed the file, by Authenticode, offline: true with who = the certificate's name when it checks out. */
bool anr_signer(const std::wstring& path, std::wstring* who);

/* The release's name for a player from a tag or a zip's name: "V.B20" from "FG-V.B20" or "anr-fg-V.B20-addon.zip";
 * "" when neither. */
std::string anr_version_of(const std::string& tag_or_zip);

#endif
