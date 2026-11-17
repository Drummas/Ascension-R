/*
 * Ascension-R -- the opening movie ended as it starts (patches.skip_opening_movie)
 *
 * The title's movie player (func_003F5748, every frame) ends a movie its boot sequence (func_0020848C) took as
 * skippable when the first connected pad holds a face button: bit 0 of the word at 0x9DD130, which func_003F5558
 * keeps from that sequence, then the pad's buttons at +0xB4 of its entry (nine of 400 bytes from 0x941660) masked
 * with 0xF0. Both pass to func_002EA0D4, the title's own skip. The sequence keeps the movie's name at 0x8CEC08, as
 * the title's scripts give it ("openingInt6"); its tests of the name (func_0052BAE4) ignore case, and so does this.
 *
 * With the patch on, both read as set while that name is OpeningInt6, the movie before the main menu: it ends on
 * its first frame as if a face button had been pressed, on a first start too (where the title does not take it as
 * skippable). The other movies stay as the title has them (docs/notes/2026-11-17-skip-movies-review.md).
 */
#include "ppu_recomp.h"
#include <stdint.h>
#include <stdio.h>

extern "C" int g_gowa_patch_skip_opening_movie;

static const uint32_t MOVIE_NAME = 0x008CEC08;   /* the boot sequence's copy of the movie's name, 0x37 bytes */
static const uint32_t AT_SKIPPABLE = 0x003F6A1C; /* cmpwi r3,0 on the word's bit 0 */
static const uint32_t AT_BUTTONS = 0x003F6A8C;   /* cmpwi r3,0 on the pad's buttons & 0xF0 */

static int is_opening(void)
{
    static const char want[] = "openingint6";   /* with its terminator, in lower case */
    for (uint32_t i = 0; i < sizeof want; i++) {
        uint8_t c = vm_read8(MOVIE_NAME + i);
        if (c >= 'A' && c <= 'Z') c = (uint8_t)(c + ('a' - 'A'));
        if (c != (uint8_t)want[i]) return 0;
    }
    return 1;
}

/* Before the two compares: r3 the bit, then the buttons. */
extern "C" void gowa_skip_opening_movie(ppu_context* ctx, uint32_t addr)
{
    if (!g_gowa_patch_skip_opening_movie || !is_opening()) return;
    if (addr == AT_SKIPPABLE) {
        ctx->gpr[3] = 1;
    } else if (addr == AT_BUTTONS) {
        ctx->gpr[3] = 0x80;
        static volatile long said;
        if (!said) {
            said = 1;
            fprintf(stderr, "[movies] the opening movie ended as it started (Skip Opening Movie)\n");
        }
    }
}
