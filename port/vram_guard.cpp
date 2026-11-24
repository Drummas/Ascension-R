/*
 * Ascension-R -- the game's VRAM manager kept from wrecking what it holds (scripts/ppu_hooks.json)
 *
 * Issue #9: at the Delphi temple, on one PC and in every session, the game printed "invalid size" and then 482
 * "CopyLocalMemory ... offset error" lines, the textures broke, and a session froze. Its VRAM manager keeps a stack of
 * blocks growing down from the top of its pool (func_0039E3F8), which takes the size it is given: a negative one
 * moves the top up instead of down, and the blocks after it overlap others or run past local memory. A texture's size
 * is [texture + 0x20] - [texture + 0x1C], the end of its data less its start (func_0039B93C). The defragmenter
 * (func_0039F06C) moves a block with the size it has, through MoveLocalMemory (func_003A2ADC) and CopyLocalMemory
 * (func_003A2690), 16 MB at a time: with a negative one, over the blocks after it and then, past local memory, over
 * main memory. The game's own checks print "invalid size" and stop on a trap, which on a PS3 would have ended the game
 * and which the lift leaves out.
 *
 * What gives a block such a size: the streaming pass trims the oldest texture's block (func_0039EA58), cutting the
 * mips above the ones it keeps off the block's front, and it takes a texture loaded with only its smaller mips too, for
 * which the cut is larger than the block (issues #7 and #9, found with #7's save in HRTN). gowa_vram_cut makes such a
 * cut nothing. The others stay for any other way: they say it in the log, with what a texture held, and keep the
 * damage from spreading: such a texture or allocation gets an empty block, and a move past local memory does not
 * happen. A size made negative on purpose (one replay of the temple) printed one line and nothing else.
 *
 * With 0.1.0-alpha.7 the same came the other way in: the texture mover (func_003A0000), which grows a streamed texture
 * into a larger block, took a size of -15 MB from a range that ends before it starts, and the bytes the frame had
 * moved went down by as much, past its budget. Its size is checked now too, and the run compactor's said
 * (docs/notes/2026-11-12-temple-textures.md).
 */
#include "ppu_recomp.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static const uint32_t GCM_STATE = 0x00A23500;   /* the game's: +0x8 the size of local memory its checks use */

static int is_there(uint32_t addr, uint32_t bytes)
{
    MEMORY_BASIC_INFORMATION mi;
    if (!VirtualQuery(vm_base + addr, &mi, sizeof mi) || mi.State != MEM_COMMIT) return 0;
    return (uint8_t*)mi.BaseAddress + mi.RegionSize >= vm_base + (uint64_t)addr + bytes;
}

/* func_0039B93C at its first branch: r31 the texture, r3 its data's size as the function took it. */
extern "C" void gowa_vram_texture(ppu_context* ctx, uint32_t)
{
    const uint32_t size = (uint32_t)ctx->gpr[3];
    if (size < 0x10000000u) return;   /* within local memory's 256 MB; past it, or negative */
    static volatile LONG said;
    const uint32_t tex = (uint32_t)ctx->gpr[31];
    if (InterlockedIncrement(&said) <= 8) {
        fprintf(stderr, "[vram] texture 0x%08X: its data ends before it starts or is past local memory, size 0x%08X, "
                        "from 0x%08X: given an empty block\n", tex, size, (uint32_t)ctx->lr);
        if (is_there(tex, 0x50)) {
            fprintf(stderr, "[vram]   0x%08X:", tex);
            for (uint32_t k = 0; k < 0x50; k += 4) fprintf(stderr, "%s %08X", k && !(k & 0xF) ? " |" : "", vm_read32(tex + k));
            fprintf(stderr, "\n");
        }
        fflush(stderr);
    }
    ctx->gpr[3] = 0;
}

/* The pool's globals: its top ([0x9B1DC0], an offset: all the room below it), the table of block descriptors (0x9AF51C,
 * its count at 0x9B1DBC; a descriptor's +8 the block's offset, +0xC its size, +0x18 its texture), the moves queued
 * (0x9B2834, which the processor runs and empties at each frame's end), the bytes the manager's pass has moved
 * ([0x9AF4BC], zeroed as each pass starts) and its budget for a frame ([0x83CD2C]). */
static const uint32_t POOL_TOP = 0x009B1DC0, BLOCKS = 0x009AF51C, BLOCK_COUNT = 0x009B1DBC, MOVES = 0x009B2834,
                      MOVED = 0x009AF4BC, BUDGET = 0x0083CD2C;

static int pool_there()
{
    static const int there = is_there(MOVED, 0x009B2E40 - MOVED) && is_there(BUDGET, 4);   /* once */
    return there;
}

/* The pool as it stands: its top, the live blocks, and the space between their lowest offset and their highest end
 * that they do not cover (holes, which only the defragmenter's moves give back). */
struct PoolState {
    uint32_t top, blocks, count, lo, hi, largest;
    uint64_t live, holes;
};

static void pool_state(PoolState* s)
{
    memset(s, 0, sizeof *s);
    s->top = vm_read32(POOL_TOP);
    s->count = vm_read32(BLOCK_COUNT);
    uint32_t lo = 0xFFFFFFFFu;
    uintptr_t rb = 0, re = 0;   /* the committed region the last descriptor was in: one query for most of them */
    for (uint32_t i = 0; i < s->count && i < 4096; i++) {
        const uint32_t d = vm_read32(BLOCKS + 4 * i);
        if (!d) continue;
        const uintptr_t p = (uintptr_t)(vm_base + d);
        if (p < rb || p + 0x20 > re) {
            MEMORY_BASIC_INFORMATION mi;
            if (!VirtualQuery((const void*)p, &mi, sizeof mi) || mi.State != MEM_COMMIT) continue;
            rb = (uintptr_t)mi.BaseAddress;
            re = rb + mi.RegionSize;
            if (p + 0x20 > re) continue;
        }
        const uint32_t off = vm_read32(d + 8), sz = vm_read32(d + 0xC);
        if (sz >= 0x10000000u) continue;
        s->blocks++;
        s->live += sz;
        if (off < lo) lo = off;
        if (off + sz > s->hi) s->hi = off + sz;
        if (sz > s->largest) s->largest = sz;
    }
    s->lo = s->blocks ? lo : 0;
    const uint64_t span = s->hi > s->lo ? s->hi - s->lo : 0;
    s->holes = span > s->live ? span - s->live : 0;
}

/* The VRAM manager (func_003A0780), once a frame: it moves and compacts blocks only when the RSX has released label
 * 0x4E with the frame counter at 0x9B227C, and otherwise leaves the frame alone (docs/notes/2026-11-12-temple-textures.md).
 * Issue #39: with Unlock FPS the pool ran short as a cinematic loaded, with 32-38 MB of holes and no move queued, as if
 * it had left most frames alone. Counted: its calls (gowa_vram_manager, on entry) and the ones that went on to its pass
 * (gowa_vram_manager_works, at 0x003A0888), in windows of 600 calls. On this PC it made its pass in half of them at 60
 * frames a second and in half to all of them unlocked, and at the reporter's next two shortages in 574 and 599 of 600:
 * the guess does not hold. A shortage's line says the last window's; a window with the pass in fewer than a quarter is
 * said, once a minute at most; GOWA_VRAM_MANAGER_LOG=1 says every window. On the game's main thread alone. */
static int s_mgr_calls, s_mgr_works;            /* this window's */
static int s_mgr_last_calls, s_mgr_last_works;  /* the last whole window's */
static int s_mgr_passed;                        /* the last call went on to its pass */

/* Issue #39, test build 2's reports: the pool ran short as a level loaded, once full (191.9 MB live, 0.3 MB of holes)
 * and once with 32.8 MB of holes. Each load is followed now. The archives a level opens (under WAD/, said by the file
 * system from whichever thread opens them) open a window on the game's main thread, which closes 4 s after the last
 * of them (60 s at most) and says the pool before the load, at its lowest (the least room an allocation found, the
 * blocks counted again each 256 KB lower) and after it, with the frames the manager made its pass in and the bytes
 * those passes moved. So a load that went through shows how close it came, and one at an unlocked frame rate can be
 * set beside one at 60. */
static SRWLOCK s_files_lock = SRWLOCK_INIT;
static struct { char last[40], first[40], level[40]; int n; } s_files;   /* since the main thread took them */
static volatile LONG s_files_n;

extern "C" void vram_guard_file_opened(const char* path, int opened)
{
    (void)opened;
    if (!path || !strstr(path, "/WAD/")) return;
    const char* b = strrchr(path, '/');
    b = b ? b + 1 : path;
    size_t n = strlen(b);
    if (n > 6 && !_stricmp(b + n - 6, ".PATCH")) n -= 6;   /* the probe for a mod's patch, which comes first */
    if (n <= 4 || n - 4 >= sizeof s_files.last || _strnicmp(b + n - 4, ".WAD", 4)) return;
    char name[40];
    memcpy(name, b, n - 4);
    name[n - 4] = 0;
    AcquireSRWLockExclusive(&s_files_lock);
    if (strcmp(name, s_files.last)) {   /* the probe and the archive itself: one file */
        snprintf(s_files.last, sizeof s_files.last, "%s", name);
        if (!s_files.n) snprintf(s_files.first, sizeof s_files.first, "%s", name);
        if (!s_files.level[0] && _strnicmp(name, "R_", 2))   /* R_: a resource's archive, not a level's */
            snprintf(s_files.level, sizeof s_files.level, "%s", name);
        InterlockedExchange(&s_files_n, ++s_files.n);
    }
    ReleaseSRWLockExclusive(&s_files_lock);
}

static int files_take(char* first, char* level)
{
    if (!InterlockedCompareExchange(&s_files_n, 0, 0)) return 0;
    AcquireSRWLockExclusive(&s_files_lock);
    const int n = s_files.n;
    snprintf(first, 40, "%s", s_files.first);
    snprintf(level, 40, "%s", s_files.level);
    s_files.n = 0;
    s_files.first[0] = s_files.level[0] = 0;
    InterlockedExchange(&s_files_n, 0);
    ReleaseSRWLockExclusive(&s_files_lock);
    return n;
}

/* Counted all session on the game's main thread: its frames (the manager's calls), the manager's passes and the bytes
 * they moved, the pool's allocations, the streaming pass's trims (func_0039EA58: a texture that counts as old, its
 * stamp [0x83CD44] = 240 frames behind the frame counter at 0x9B9988, loses its top mips off its block's front and
 * leaves a hole there) and the texture mover's grows (func_003A0000: a streamed texture into a larger block, a new
 * block and a move). A frame count is no time: unlocked at 144 frames a second 240 frames is 1.7 s, where the title
 * waited 4 s at 60. A load's line, and GOWA_VRAM_STATS=<seconds>'s, say what they did. */
struct PoolCounts {
    uint64_t frames, passes, moved, allocs, alloc_bytes, trims, trim_bytes, grows, grow_bytes;
};
static PoolCounts s_tot;

static PoolCounts counts_since(const PoolCounts& a)
{
    PoolCounts d;
    d.frames = s_tot.frames - a.frames;
    d.passes = s_tot.passes - a.passes;
    d.moved = s_tot.moved - a.moved;
    d.allocs = s_tot.allocs - a.allocs;
    d.alloc_bytes = s_tot.alloc_bytes - a.alloc_bytes;
    d.trims = s_tot.trims - a.trims;
    d.trim_bytes = s_tot.trim_bytes - a.trim_bytes;
    d.grows = s_tot.grows - a.grows;
    d.grow_bytes = s_tot.grow_bytes - a.grow_bytes;
    return d;
}

static void counts_say(char* out, size_t n, const PoolCounts& d)
{
    snprintf(out, n, "the manager's pass in %llu frames, %.1f MB moved; %llu allocations (%.1f MB), %llu trims "
                     "(%.1f MB), %llu grows (%.1f MB)", (unsigned long long)d.passes, d.moved / 1048576.0,
             (unsigned long long)d.allocs, d.alloc_bytes / 1048576.0, (unsigned long long)d.trims,
             d.trim_bytes / 1048576.0, (unsigned long long)d.grows, d.grow_bytes / 1048576.0);
}

static struct {
    int on, has_level, files, at_budget, low_frame;
    char name[40];
    ULONGLONG t0, last_file;
    PoolState before, low, after;
    PoolCounts at0;                  /* s_tot as it opened */
    int64_t low_left, walked_left;   /* the least room an allocation left (below 0: one that did not fit) */
    uint32_t moved_max;
} s_load;

static void load_say(void)
{
    const PoolState* st[3] = { &s_load.before, &s_load.low, &s_load.after };
    char part[3][120];
    for (int i = 0; i < 3; i++)
        snprintf(part[i], sizeof part[i], "%s %.1f MB, %.1f MB in %u blocks, %.1f MB of holes",
                 i == 1 ? "room left" : "room", (i == 1 ? (double)s_load.low_left : (double)st[i]->top) / 1048576.0,
                 st[i]->live / 1048576.0, st[i]->blocks, st[i]->holes / 1048576.0);
    char more[32] = "", counts[256];
    if (s_load.files > 1) snprintf(more, sizeof more, " and %d more", s_load.files - 1);
    const PoolCounts d = counts_since(s_load.at0);
    counts_say(counts, sizeof counts, d);
    fprintf(stderr, "[vram] load of %s.WAD%s, %.1f s, %llu frames: the pool before it %s; at its lowest (frame %d) %s; "
                    "after it %s; %s; at most %.1f MB moved in a frame, %d at its %.0f MB budget\n", s_load.name, more,
            (GetTickCount64() - s_load.t0) / 1000.0, (unsigned long long)d.frames, part[0], s_load.low_frame, part[1],
            part[2], counts, s_load.moved_max / 1048576.0, s_load.at_budget, vm_read32(BUDGET) / 1048576.0);
    fflush(stderr);
}

/* GOWA_VRAM_STATS=<seconds>: every so many seconds, what the counts did and the pool as it stands. */
static void stats_frame(ULONGLONG now)
{
    static int every = -1;
    if (every < 0) {
        const char* e = getenv("GOWA_VRAM_STATS");
        every = e ? atoi(e) : 0;
    }
    if (every <= 0) return;
    static ULONGLONG last;
    static PoolCounts at;
    if (!last) {
        last = now;
        at = s_tot;
        return;
    }
    if (now - last < (ULONGLONG)every * 1000u) return;
    const PoolCounts d = counts_since(at);
    PoolState s;
    pool_state(&s);
    char counts[256];
    counts_say(counts, sizeof counts, d);
    const double secs = (now - last) / 1000.0;
    fprintf(stderr, "[vram] %.1f s: %llu frames (%.0f a second); %s; the pool room %.1f MB, %.1f MB in %u blocks, %.1f MB "
                    "of holes\n", secs, (unsigned long long)d.frames, d.frames / secs, counts, s.top / 1048576.0,
            s.live / 1048576.0, s.blocks, s.holes / 1048576.0);
    fflush(stderr);
    last = now;
    at = s_tot;
}

/* At the manager's call, once a frame: the frame and its last pass counted, a load's files, and its end. */
static void load_frame(void)
{
    s_tot.frames++;
    if (s_mgr_passed) {
        const uint32_t moved = vm_read32(MOVED), budget = vm_read32(BUDGET);
        s_tot.passes++;
        s_tot.moved += moved;
        if (s_load.on) {
            if (moved > s_load.moved_max) s_load.moved_max = moved;
            if (budget && moved >= budget) s_load.at_budget++;
        }
    }
    stats_frame(GetTickCount64());
    char first[40], level[40];
    const int n = files_take(first, level);
    const ULONGLONG now = GetTickCount64();
    if (n) {
        if (!s_load.on) {
            memset(&s_load, 0, sizeof s_load);
            s_load.on = 1;
            s_load.t0 = now;
            pool_state(&s_load.before);
            s_load.low = s_load.before;
            s_load.low_left = s_load.walked_left = (int32_t)s_load.before.top;
            s_load.at0 = s_tot;
        }
        if (level[0] && !s_load.has_level) {
            snprintf(s_load.name, sizeof s_load.name, "%s", level);
            s_load.has_level = 1;
        } else if (!s_load.name[0]) {
            snprintf(s_load.name, sizeof s_load.name, "%s", first);
        }
        s_load.files += n;
        s_load.last_file = now;
    }
    if (!s_load.on) return;
    if (now - s_load.last_file >= 4000 || now - s_load.t0 >= 60000) {
        pool_state(&s_load.after);
        load_say();
        s_load.on = 0;
    }
}

extern "C" void gowa_vram_manager(ppu_context*, uint32_t)
{
    if (pool_there()) load_frame();
    s_mgr_passed = 0;
    if (++s_mgr_calls < 600) return;
    s_mgr_last_calls = s_mgr_calls;
    s_mgr_last_works = s_mgr_works;
    s_mgr_calls = s_mgr_works = 0;
    static int all = -1;
    if (all < 0) { const char* e = getenv("GOWA_VRAM_MANAGER_LOG"); all = e && *e == '1'; }
    static ULONGLONG said;
    const ULONGLONG now = GetTickCount64();
    if (all || (s_mgr_last_works * 4 < s_mgr_last_calls && (!said || now - said >= 60000))) {
        said = now;
        fprintf(stderr, "[vram] the manager did its pass in %d of its last %d frames; in the others the RSX had not "
                        "released label 0x4E yet\n", s_mgr_last_works, s_mgr_last_calls);
        fflush(stderr);
    }
}

extern "C" void gowa_vram_manager_works(ppu_context*, uint32_t)
{
    s_mgr_works++;
    s_mgr_passed = 1;
}

/* What fills the pool, said at its first shortage: the live blocks by size, those of a texture, and the eight largest
 * with their texture's data range ([texture + 0x1C], [+0x20]). */
static void pool_profile(void)
{
    static const uint32_t floor_of[5] = { 0x400000u, 0x100000u, 0x40000u, 0x10000u, 0u };
    static const char* const label[5] = { "4 MB and up", "1-4 MB", "256 KB-1 MB", "64-256 KB", "under 64 KB" };
    struct Big { uint32_t d, off, size; };
    Big big[8] = {};
    uint32_t n[5] = { 0 }, tex_n = 0;
    uint64_t bytes[5] = { 0 }, tex_bytes = 0;
    const uint32_t count = vm_read32(BLOCK_COUNT);
    for (uint32_t i = 0; i < count && i < 4096; i++) {
        const uint32_t d = vm_read32(BLOCKS + 4 * i);
        if (!d || !is_there(d, 0x20)) continue;
        const uint32_t off = vm_read32(d + 8), sz = vm_read32(d + 0xC);
        if (sz >= 0x10000000u) continue;
        int c = 0;
        while (sz < floor_of[c]) c++;
        n[c]++;
        bytes[c] += sz;
        if (vm_read32(d + 0x18)) {
            tex_n++;
            tex_bytes += sz;
        }
        for (int k = 0; k < 8; k++)
            if (sz > big[k].size) {
                memmove(&big[k + 1], &big[k], (size_t)(7 - k) * sizeof big[0]);
                big[k] = Big{ d, off, sz };
                break;
            }
    }
    fprintf(stderr, "[vram]   the live blocks by size:");
    for (int c = 0; c < 5; c++) fprintf(stderr, "%s %s %u (%.1f MB)", c ? "," : "", label[c], n[c], bytes[c] / 1048576.0);
    fprintf(stderr, "; %u of them a texture's (%.1f MB)\n", tex_n, tex_bytes / 1048576.0);
    for (int k = 0; k < 8 && big[k].size; k++) {
        const uint32_t t = vm_read32(big[k].d + 0x18);
        fprintf(stderr, "[vram]   block 0x%08X: offset 0x%08X, %.2f MB, texture 0x%08X", big[k].d, big[k].off,
                big[k].size / 1048576.0, t);
        if (t && is_there(t, 0x24)) fprintf(stderr, " (its data 0x%X..0x%X)", vm_read32(t + 0x1C), vm_read32(t + 0x20));
        fprintf(stderr, "\n");
    }
}

/* An allocation about to fail, said with the pool as it stands (#30: once in a playthrough a texture got no block, and
 * the game wrote its fields to address 0, which on a PS3 ends the game). The pool is a stack: a block is cut off
 * below its top ([0x9B1DC0], an offset), 128-byte aligned, and an allocation fails when the top is lower than that.
 * Blocks freed above the top leave holes that only the defragmenter's moves, a budget a frame, give back. So the line
 * says whether the pool is full or only not compacted yet: its top (all the room left below it), the live blocks
 * (the table of descriptor pointers at 0x9AF51C, its count at 0x9B1DBC; +8 a block's offset, +0xC its size), the
 * space between their lowest offset and their highest end that they do not cover, and the moves queued (0x9B2834).
 * The allocator may still reuse a block of the same key instead (its first loop): "may" fail. The first shortage also
 * says what fills the pool (pool_profile). During a load, the room each allocation leaves counts toward the load's
 * lowest (taken here, as the allocation starts: after it the top is that much lower). */
static void vram_alloc_short(ppu_context* ctx, uint32_t size)
{
    if (!pool_there()) return;
    const uint32_t top = vm_read32(POOL_TOP), need = (size + 0x7Fu) & ~0x7Fu;
    const int64_t left = (int64_t)(int32_t)top - (int64_t)need;
    s_tot.allocs++;
    s_tot.alloc_bytes += need;
    if (s_load.on && left < s_load.low_left) {
        s_load.low_left = left;
        s_load.low_frame = (int)(s_tot.frames - s_load.at0.frames);
        if (s_load.walked_left - left >= 0x40000 || left < 0) {
            pool_state(&s_load.low);
            s_load.walked_left = left;
        }
    }
    if ((int32_t)top >= (int32_t)need) return;
    static volatile LONG said;
    const LONG n = InterlockedIncrement(&said);
    if (n > 8 && (n & (n - 1))) return;
    PoolState s;
    pool_state(&s);
    fprintf(stderr, "[vram] the pool is short: 0x%X bytes asked for from 0x%08X, its top at 0x%X (all the room below it); "
                    "%u live blocks of %u in the table, %.1f MB, the largest %.1f MB, from 0x%X to 0x%X with %.1f MB of holes "
                    "between them; %u moves queued (%ld so far); the manager's pass in %d of its last %d frames\n", size,
            (uint32_t)ctx->lr, top, s.blocks, s.count, s.live / 1048576.0, s.largest / 1048576.0, s.lo, s.hi,
            s.holes / 1048576.0, vm_read32(MOVES), (long)n, s_mgr_last_works, s_mgr_last_calls);
    if (n == 1) pool_profile();
    fflush(stderr);
}

/* The pool's allocator (func_0039E3F8) on entry: r4 the size, from a texture (func_0039B93C), from func_0039F7C8 at
 * [[r30] + 0x20], or from the block the defragmenter moves. Past local memory or negative, it is made 0: a negative
 * one would move the pool's top up. */
extern "C" void gowa_vram_alloc(ppu_context* ctx, uint32_t)
{
    const uint32_t size = (uint32_t)ctx->gpr[4];
    if (size < 0x10000000u) {
        vram_alloc_short(ctx, size);
        return;
    }
    static volatile LONG said;
    if (InterlockedIncrement(&said) <= 8) {
        fprintf(stderr, "[vram] an allocation of 0x%08X bytes, from 0x%08X: made 0\n", size, (uint32_t)ctx->lr);
        fflush(stderr);
    }
    ctx->gpr[4] = 0;
}

/* func_003A0000 (and func_0039FFFC, the same code a word earlier) moves a streamed texture's data into the larger block
 * it grows into: the texture at the head of [0x9B26AC] (r28), its range [+0x1C, +0x20), out of its block (r30) into
 * [0x9B1DEC] (r31). Here r6 is the range's size, about to be added to the bytes the frame has moved ([0x9AF4BC]) and
 * queued, or moved at once. Nothing checked it: a range that ends before it starts took a negative size into the
 * frame's 16 MB budget, after which the defragmenter moved without a limit (issue #9, 0.1.0-alpha.7: four moves of
 * -15 to -105 MB, then hundreds past local memory). Past local memory or negative, it is made 0, and said with the
 * texture and both blocks. GOWA_VRAM_STREAM_GUARD=0 leaves it as the game has it, to try the guard. */
extern "C" void gowa_vram_stream(ppu_context* ctx, uint32_t)
{
    const uint32_t size = (uint32_t)ctx->gpr[6];
    if (size < 0x10000000u) {
        s_tot.grows++;
        s_tot.grow_bytes += size;
        return;
    }
    static int on = -1;
    if (on < 0) {
        const char* e = getenv("GOWA_VRAM_STREAM_GUARD");
        on = !(e && e[0] == '0');
    }
    static volatile LONG said;
    if (InterlockedIncrement(&said) <= 8) {
        const uint32_t tex = (uint32_t)ctx->gpr[28], from = (uint32_t)ctx->gpr[30], into = (uint32_t)ctx->gpr[31];
        fprintf(stderr, "[vram] streamed texture 0x%08X: its range 0x%08X..0x%08X ends before it starts or is past local "
                        "memory, size 0x%08X, from 0x%08X: %s\n", tex, (uint32_t)ctx->gpr[26],
                (uint32_t)ctx->gpr[26] + size, size, (uint32_t)ctx->lr, on ? "moved as 0 bytes" : "left as it is");
        for (int k = 0; k < 2; k++) {
            const uint32_t b = k ? into : from;
            if (is_there(b, 0x20))
                fprintf(stderr, "[vram]   %s block 0x%08X: offset 0x%08X, size 0x%08X\n", k ? "into" : "from", b,
                        vm_read32(b + 0x8), vm_read32(b + 0xC));
        }
        if (is_there(tex, 0x50)) {
            fprintf(stderr, "[vram]   0x%08X:", tex);
            for (uint32_t k = 0; k < 0x50; k += 4) fprintf(stderr, "%s %08X", k && !(k & 0xF) ? " |" : "", vm_read32(tex + k));
            fprintf(stderr, "\n");
        }
        fflush(stderr);
    }
    if (on) ctx->gpr[6] = 0;
}

/* func_0039F3C4 packs a run of blocks up against the one above: r3 the run's size, the sum of its blocks' sizes, r29
 * its first block's index and r30 the one past its last, in the table at 0x9AF51C. A block's size is checked when it
 * is allocated (gowa_vram_alloc), so a bad sum is a block whose size went bad after: said with the run's blocks, and
 * left as it is (the moves that follow are guarded, and the blocks' new places come from it). */
extern "C" void gowa_vram_runs(ppu_context* ctx, uint32_t)
{
    const uint32_t size = (uint32_t)ctx->gpr[3];
    if (size < 0x10000000u) return;
    static volatile LONG said;
    if (InterlockedIncrement(&said) > 4) return;
    const uint32_t first = (uint32_t)ctx->gpr[29], end = (uint32_t)ctx->gpr[30];
    fprintf(stderr, "[vram] a run of blocks %u..%u, size 0x%08X, from 0x%08X: a block's size went bad after it was "
                    "allocated\n", first, end, size, (uint32_t)ctx->lr);
    for (uint32_t i = first; i < end && i < first + 8 && i < 0xA28; i++) {
        const uint32_t b = vm_read32(0x009AF51C + 4 * i);
        if (b && is_there(b, 0x20))
            fprintf(stderr, "[vram]   block %u 0x%08X: offset 0x%08X, size 0x%08X, +0x18 0x%08X, +0x1C 0x%08X\n", i, b,
                    vm_read32(b + 0x8), vm_read32(b + 0xC), vm_read32(b + 0x18), vm_read32(b + 0x1C));
    }
    fflush(stderr);
}

/* func_0039EA58 trims a texture's block: it cuts [texture + 0x1C] bytes, the mips above the ones the texture keeps,
 * off the block's front, and moves its offset and RSX address up by as much. That holds for a block with the whole
 * chain, [0, [texture + 0x20]). The streaming pass (around 0x003A0D88) also takes, once it is the oldest, a texture
 * loaded with only its smaller mips, whose block is [+0x20] - [+0x1C] bytes: the cut is larger than the block, its
 * size goes negative and its offset past its data, and the moves after it wreck local memory (#9; #7: one 1024x1024
 * texture at the Sparta cinematic's level, cut by 640 KB from a 43 KB block every frame).
 * At 0x0039EB1C r29 is the cut, r4 the block's size, r30 the block, r31 the texture. A cut larger than the block is
 * made what the block holds in front of the kept mips: nothing, for such a block. The trim then changes nothing in
 * place, and its other work stays as the game has it. So that the pass takes another texture next, this one's LRU
 * stamp (+8 of its block's state entry, in the table at [0x9B2298]) is moved on by the 240 frames the pass waits
 * before a texture counts as old; a pass that takes it every frame finds nothing to free and stays short of memory. */
extern "C" void gowa_vram_cut(ppu_context* ctx, uint32_t)
{
    const uint32_t cut = (uint32_t)ctx->gpr[29], size = (uint32_t)ctx->gpr[4];
    s_tot.trims++;
    if (cut <= size) {
        s_tot.trim_bytes += cut;
        return;
    }
    const uint32_t tex = (uint32_t)ctx->gpr[31], blk = (uint32_t)ctx->gpr[30];
    const uint32_t end = is_there(tex, 0x48) ? vm_read32(tex + 0x20) : 0;
    const uint32_t lead = end >= size ? end - size : 0;   /* where in the chain the block begins */
    const uint32_t fixed = cut >= lead && cut - lead <= size ? cut - lead : 0;
    ctx->gpr[29] = fixed;
    s_tot.trim_bytes += fixed;
    uint32_t stamp = 0;
    if (is_there(0x009B2298, 8)) {
        const int32_t d = (int32_t)(blk - vm_read32(0x009B229C));
        const uint32_t st = vm_read32(0x009B2298) + (uint32_t)((d / 128) * 16);   /* srawi 7 + addze: toward zero */
        if (is_there(st, 16)) {
            stamp = vm_read32(st + 8);
            if (stamp) vm_write32(st + 8, stamp + 240);
        }
    }
    static volatile LONG said;
    const LONG n = InterlockedIncrement(&said);
    if (n <= 8 || !(n & (n - 1))) {
        fprintf(stderr, "[vram] texture 0x%08X: a trim of 0x%X bytes from a block of 0x%X that holds only its mips from "
                        "0x%X made 0x%X; its stamp 0x%X put 240 frames on (%ld so far)\n", tex, cut, size, lead, fixed,
                stamp, (long)n);
        fflush(stderr);
    }
}

/* MoveLocalMemory (func_003A2ADC) on entry: r3 the destination, r4 the source, r5 the size, as offsets in local
 * memory. A move either side of which runs past local memory is made a move of nothing. */
extern "C" void gowa_vram_move(ppu_context* ctx, uint32_t)
{
    const uint64_t dst = (uint32_t)ctx->gpr[3], src = (uint32_t)ctx->gpr[4], size = (uint32_t)ctx->gpr[5];
    const uint64_t local = vm_read32(GCM_STATE + 0x8);
    if (size < 0x20000000u && src + size <= local && dst + size <= local) return;
    static volatile LONG said;
    if (InterlockedIncrement(&said) <= 8) {
        fprintf(stderr, "[vram] a move of 0x%08llX bytes from 0x%08llX to 0x%08llX runs past local memory (0x%llX), "
                        "from 0x%08X: left out\n", (unsigned long long)size, (unsigned long long)src,
                (unsigned long long)dst, (unsigned long long)local, (uint32_t)ctx->lr);
        fflush(stderr);
    }
    ctx->gpr[5] = 0;
}
