#!/usr/bin/env python3
"""The SDKs a Kit release takes, fetched beside this tree.

`gowa.py package kit` packs what a player's PC needs and what the launcher loads, and most of what goes beside the exe
is somebody else's: SDL3, AMD's FidelityFX SDK, NVIDIA's Streamline, an embeddable Python, the clang the Kit carries,
and the FFmpeg the release adds to it. A release machine keeps them beside the tree (the Release workflow's header says
where). This script fetches each one from where its maker publishes it, into the place `gowa.py` looks for it, and
checks every download against the SHA-256 `gowa.py` pins, so a release can also be packaged on a runner that has only
the Windows SDK and LLVM.

    python scripts/release_sdks.py            what is missing, fetched
    python scripts/release_sdks.py --check    only say what is there and what is not

Beside the tree: sdl3/, fsr-sdk/, streamline-sdk/, python-embed/, llvm-license/, and ffmpeg/ (the release FFmpeg's
headers). In the tree: ffmpeg-release/, which `gowa.py ffmpeg` builds in and .gitignore keeps out of a commit.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BESIDE = os.path.dirname(ROOT)
sys.path.insert(0, HERE)
import gowa  # noqa: E402  the versions, the SHA-256s and the folders a release takes them from

GOWA_PY = os.path.join(HERE, "gowa.py")
FSR_VERSION = "2.4.0"
FSR_URL = "https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK/archive/refs/tags/v%s.tar.gz" % FSR_VERSION
SDL3_URL = "https://github.com/libsdl-org/SDL/releases/download/release-%s/SDL3-devel-%s-VC.zip" % (
    gowa.SDL3_VERSION, gowa.SDL3_VERSION)
STREAMLINE_URL = "https://github.com/NVIDIA-RTX/Streamline/releases/download/v%s/streamline-sdk-v%s.zip" % (
    gowa.STREAMLINE_VERSION, gowa.STREAMLINE_VERSION)
PYTHON_URL = "https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip" % (gowa.KIT_PYTHON, gowa.KIT_PYTHON)
LLVM_LICENSE_URL = "https://raw.githubusercontent.com/llvm/llvm-project/llvmorg-%s/%s/LICENSE.TXT"


def say(text):
    print(text, flush=True)


def die(text):
    say("release_sdks: " + text)
    raise SystemExit(1)


def digest(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(url, name, want=None):
    """url into a temporary file, checked against want (a SHA-256) when gowa.py pins one. Returns its path."""
    tmp_dir = tempfile.mkdtemp(prefix="release-sdks-")
    path = os.path.join(tmp_dir, name)
    say("  " + url)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Ascension-R release"})) as r:
        with open(path, "wb") as f:
            shutil.copyfileobj(r, f)
    if want and digest(path) != want:
        die("%s is not the file gowa.py pins (SHA-256 %s, not %s)" % (name, want, digest(path)))
    return path


def unpack(archive, into):
    """An archive into into: a zip, or a .tar.xz/.tar.gz."""
    os.makedirs(into, exist_ok=True)
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(into)
    else:
        with tarfile.open(archive) as t:
            t.extractall(into, filter="data")
    return into


def underneath(folder, rel):
    """The folder at or below folder that holds rel (with /), or None: an SDK's archive has a folder of its own
    inside, and that folder is the SDK."""
    for d, _, _ in os.walk(folder):
        if os.path.isfile(os.path.join(d, rel.replace("/", os.sep))):
            return d
    return None


def place(found, to):
    """found (an unpacked folder) becomes to, emptying it first."""
    shutil.rmtree(to, ignore_errors=True)
    os.makedirs(os.path.dirname(to), exist_ok=True)
    shutil.move(found, to)
    return to


def llvm_bin():
    for c in (os.environ.get("GOWA_LLVM_BIN"), gowa.load_local().get("llvm_bin"),
              os.path.join(BESIDE, "llvm", "bin"), r"C:\Program Files\LLVM\bin"):
        if c and all(os.path.isfile(os.path.join(c, t)) for t in ("clang-cl.exe", "lld-link.exe", "llvm-profdata.exe")):
            return c
    die("no clang-cl.exe, lld-link.exe and llvm-profdata.exe: set GOWA_LLVM_BIN to an LLVM's bin")


def sdl3(check_only):
    if gowa.find_sdl3():
        say("SDL3 %s: there, %s" % (gowa.SDL3_VERSION, gowa.find_sdl3()))
        return
    if check_only:
        say("SDL3 %s: missing (the build takes its headers, the release its DLL)" % gowa.SDL3_VERSION)
        return
    say("SDL3 %s:" % gowa.SDL3_VERSION)
    zip_path = fetch(SDL3_URL, "SDL3-devel.zip", gowa.SDL3_ZIP_SHA256)
    tmp = unpack(zip_path, tempfile.mkdtemp(prefix="sdl3-"))
    found = underneath(tmp, "include/SDL3/SDL_gamepad.h")
    if not found or not os.path.isfile(os.path.join(found, "lib", "x64", "SDL3.dll")):
        die("the SDL3 zip has no include/SDL3 and lib/x64/SDL3.dll")
    place(found, os.path.join(BESIDE, "sdl3", gowa.SDL3_VERSION, "SDL3-" + gowa.SDL3_VERSION))
    say("  -> %s" % gowa.find_sdl3())


def fsr(check_only):
    if gowa.find_fsr():
        say("FidelityFX %s: there, %s" % (FSR_VERSION, gowa.find_fsr()))
        return
    if check_only:
        say("FidelityFX %s: missing (the DLLs the release ships, signed)" % FSR_VERSION)
        return
    say("FidelityFX SDK %s:" % FSR_VERSION)
    tar = fetch(FSR_URL, "FidelityFX-SDK.tar.gz")
    tmp = unpack(tar, tempfile.mkdtemp(prefix="fsr-"))
    found = underneath(tmp, "Kits/FidelityFX/signedbin/amd_fidelityfx_loader_dx12.dll")
    if not found:
        die("the FidelityFX SDK archive has no Kits/FidelityFX/signedbin: take the SDK package from gpuopen.com")
    place(found, os.path.join(BESIDE, "fsr-sdk", "v" + FSR_VERSION))
    say("  -> %s" % gowa.find_fsr())


def streamline(check_only):
    if gowa.find_streamline():
        say("Streamline %s: there, %s" % (gowa.STREAMLINE_VERSION, gowa.find_streamline()))
        return
    if check_only:
        say("Streamline %s: missing (the signed DLLs, each by its SHA-256)" % gowa.STREAMLINE_VERSION)
        return
    say("Streamline %s:" % gowa.STREAMLINE_VERSION)
    zip_path = fetch(STREAMLINE_URL, "streamline-sdk.zip", gowa.STREAMLINE_ZIP_SHA256)
    tmp = unpack(zip_path, tempfile.mkdtemp(prefix="streamline-"))
    found = underneath(tmp, "bin/x64/sl.interposer.dll")
    if not found:
        die("the Streamline zip has no bin/x64/sl.interposer.dll")
    place(found, os.path.join(BESIDE, "streamline-sdk", "v" + gowa.STREAMLINE_VERSION))
    if not gowa.find_streamline():
        die("the Streamline DLLs are not the ones gowa.py pins by SHA-256: %s"
            % os.path.join(BESIDE, "streamline-sdk", "v" + gowa.STREAMLINE_VERSION))
    say("  -> %s" % gowa.find_streamline())


def python(check_only):
    into = os.path.join(BESIDE, "python-embed", gowa.KIT_PYTHON)
    there = os.path.isfile(os.path.join(into, "python.exe")) and os.path.isfile(os.path.join(into, gowa.KIT_PYTHON_PTH))
    if there:
        say("Python %s, embeddable: there, %s" % (gowa.KIT_PYTHON, into))
        return
    if check_only:
        say("Python %s, embeddable: missing" % gowa.KIT_PYTHON)
        return
    say("Python %s, embeddable:" % gowa.KIT_PYTHON)
    zip_path = fetch(PYTHON_URL, "python-embed.zip", gowa.KIT_PYTHON_SHA256)
    place(unpack(zip_path, tempfile.mkdtemp(prefix="python-")), into)
    say("  -> %s" % into)


def llvm_licenses(check_only):
    """llvm-project's license texts at the tag of the clang the Kit carries: kit-tree copies them in."""
    try:
        bin_dir = llvm_bin()
    except SystemExit:
        if not check_only:
            raise
        say("llvm-project licenses: missing (no clang-cl.exe to take the version from)")
        return
    version = gowa.llvm_version(bin_dir)[0]
    into = os.path.join(BESIDE, "llvm-license", "llvmorg-" + version)
    missing = [p for p in gowa.KIT_LLVM_LICENSES if not os.path.isfile(os.path.join(into, p, "LICENSE.TXT"))]
    if not missing:
        say("llvm-project licenses %s: there, %s" % (version, into))
        return
    if check_only:
        say("llvm-project licenses %s: missing %s" % (version, ", ".join(missing)))
        return
    say("llvm-project licenses, llvmorg-%s:" % version)
    for part in missing:
        path = fetch(LLVM_LICENSE_URL % (version, part), part + "-LICENSE.TXT")
        to = os.path.join(into, part)
        os.makedirs(to, exist_ok=True)
        shutil.move(path, os.path.join(to, "LICENSE.TXT"))
    say("  -> %s" % into)


def release_ffmpeg(check_only):
    """FFmpeg's two libraries from its source tarball (gowa.py ffmpeg: MinGW-w64's gcc and nasm), and the headers the
    build compiles against, in the folder find_ffmpeg looks in."""
    out = os.path.join(gowa.FFMPEG_HOME, gowa.FFMPEG_VERSION)
    have = all(os.path.isfile(os.path.join(out, dll)) for _, dll in gowa.FFMPEG_DLLS) and \
        os.path.isfile(os.path.join(out, "COPYING.LGPLv2.1")) and os.path.isfile(os.path.join(out, "FFmpeg-build.txt"))
    headers = os.path.join(BESIDE, "ffmpeg", gowa.FFMPEG_VERSION, "include", "libavcodec", "avcodec.h")
    if have and os.path.isfile(headers):
        say("FFmpeg %s: there, %s" % (gowa.FFMPEG_VERSION, out))
        return
    if check_only:
        say("FFmpeg %s: missing (%s and %s)" % (gowa.FFMPEG_VERSION, out, os.path.dirname(os.path.dirname(headers))))
        return
    missing = [t for t in ("gcc", "nasm", "mingw32-make") if not shutil.which(t)]
    if missing:
        die("FFmpeg is built with MinGW-w64's gcc, nasm and make; not on PATH: %s" % ", ".join(missing))
    tarball = os.path.join(gowa.FFMPEG_HOME, gowa.FFMPEG_TARBALL)
    if not os.path.isfile(tarball):
        say("FFmpeg %s, its source:" % gowa.FFMPEG_VERSION)
        os.makedirs(gowa.FFMPEG_HOME, exist_ok=True)
        shutil.move(fetch(gowa.FFMPEG_URL, gowa.FFMPEG_TARBALL, gowa.FFMPEG_SHA256), tarball)
    say("FFmpeg %s: building with gowa.py ffmpeg (a few minutes)" % gowa.FFMPEG_VERSION)
    rc = subprocess.call([sys.executable, GOWA_PY, "ffmpeg", "--jobs", str(max(2, os.cpu_count() or 2))])
    if rc:
        die("gowa.py ffmpeg failed: its configure or make output is above")
    src = os.path.join(gowa.FFMPEG_HOME, "src", "ffmpeg-" + gowa.FFMPEG_VERSION)
    into = os.path.join(BESIDE, "ffmpeg", gowa.FFMPEG_VERSION, "include")
    for lib in ("libavcodec", "libavutil"):
        dst = os.path.join(into, lib)
        shutil.rmtree(dst, ignore_errors=True)
        os.makedirs(dst, exist_ok=True)
        for name in os.listdir(os.path.join(src, lib)):
            if name.endswith(".h"):
                shutil.copy2(os.path.join(src, lib, name), os.path.join(dst, name))
    if not gowa.find_ffmpeg():
        die("the build did not leave headers a release build can use in %s" % into)
    say("  -> %s, headers in %s" % (out, into))


def main():
    args = parse()
    say("release_sdks: %s%s" % (ROOT, " (checking only)" if args.check else ""))
    missing = []
    for name, fn in (("SDL3", sdl3), ("FidelityFX", fsr), ("Streamline", streamline), ("Python", python),
                     ("llvm-project licenses", llvm_licenses), ("FFmpeg", release_ffmpeg)):
        try:
            fn(args.check)
        except SystemExit:
            raise
        except Exception as e:   # a network error, an archive that is not what it should be
            die("%s: %s" % (name, e))
    if not gowa.find_dxc_redist():
        missing.append("the Windows SDK's Redist\\D3D\\x64 (dxcompiler.dll and dxil.dll)")
    for what in missing:
        say("missing, and not fetched here: " + what)
    if missing and not args.check:
        die("a release needs all of them")
    return 1 if (args.check and missing) else 0


def parse():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--check", action="store_true", help="say what is there and what is not; fetch nothing")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
