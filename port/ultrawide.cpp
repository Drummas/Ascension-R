/*
 * Ascension-R -- the title's camera at the screen's width (display.ultrawide) and the field of view in play
 * (graphics.fov)
 *
 * The title keeps a camera's horizontal half-width and divides it by the aspect at +32 of its render settings for the
 * vertical one, so a wider aspect alone would crop the picture top and bottom. Both change here: the aspect, and the
 * half-width by the same factor, which leaves the vertical view as it was and adds to the sides. The title's own frustum
 * comes from the same two numbers, so what it draws follows. The 2D screens are drawn through orthographic cameras made
 * the same way, so they keep their shape in the 16:9 in the middle. scripts/ppu_hooks.json has the lift call these.
 *
 * graphics.fov: the same tangent times a factor (0.8 to 1.4), both ways at once, for the cameras of play only. Play is
 * when the camera controller (func_00314780, gowa_wide_framing) has run in the last 0.15 s: it does not during the
 * in-engine cinematics, which keep the title's own field of view. Its cameras are the ones that share the lens object
 * (+0x47C) of the camera worked out most often (the play camera, twice a frame; the others, the menus' and the HUD's at
 * a fixed 54 degrees, once). The factor eases in and out over 0.4 s at a cut between the two.
 */
#include "ppu_recomp.h"
#include "rsx_d3d12_backend.h"
#include "ps3emu/ps3_settings.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* func_003A3DD8: r4 holds 16:9, about to go to +32 of the render settings. */
extern "C" void gowa_wide_aspect(ppu_context* ctx, uint32_t)
{
    const float r = rsx_d3d12_backend_wide_ratio();
    if (r == 1.0f) return;
    const float aspect = 16.0f / 9.0f * r;
    uint32_t bits;
    memcpy(&bits, &aspect, sizeof bits);
    ctx->gpr[4] = bits;
}

/* func_003B0380: f1 the tangent of a perspective camera's field of view, about to make its half-width at +960. func_003AFDC8
 * and func_003B0380 again: f1 an orthographic camera's half-width (func_0031446C), about to be kept in f31. */
/* GOWA_FOV_PROBE=1: once a second, each camera seen since with its lens, caller, last angle and count, and how often
 * the camera controller (gowa_wide_framing) ran (field of view work). */
static int s_probe = -1;
static unsigned s_probe_ctrl;
static int probe_on(void)
{
    if (s_probe < 0) { const char* e = getenv("GOWA_FOV_PROBE"); s_probe = e && *e == '1'; }
    return s_probe;
}

static double now_s(void) { return (double)clock() / CLOCKS_PER_SEC; }
static double s_ctrl_last = -10.0;   /* when the camera controller last ran */

static float fov_setting(void)
{
    static float v = -1.0f;
    if (v < 0.0f) {
        const char* e = ps3_settings_str("graphics", "fov", "GOWA_FOV", "1");
        v = e ? (float)atof(e) : 1.0f;
        if (!(v >= 0.5f && v <= 2.0f)) v = 1.0f;
        if (v != 1.0f) fprintf(stderr, "[gowa] field of view in play: %.0f%% of the game's%c", v * 100.0f, 10);
    }
    return v;
}

extern "C" void gowa_wide_fov(ppu_context* ctx, uint32_t addr)
{
    if (addr == 0x003B05A4u) {   /* a perspective camera */
        struct Cam { uint32_t cam, lens, caller; double deg; unsigned n, window; };
        static Cam cams[16];
        static int ncam;
        static double t_probe, t_main, t_last;
        static uint32_t main_lens;
        static float k = 1.0f;
        const double now = now_s();
        const uint32_t cam = (uint32_t)ctx->gpr[31], lens = vm_read32(cam + 0x47C);
        int c = 0;
        for (; c < ncam && cams[c].cam != cam; c++) {}
        if (c == ncam && ncam < 16) { memset(&cams[ncam], 0, sizeof cams[0]); cams[ncam].cam = cam; ncam++; }
        if (c < ncam) {
            cams[c].lens = lens; cams[c].n++; cams[c].window++;
            cams[c].deg = 2.0 * atan(ctx->fpr[1]) * 57.29577951;
        }
        if (now - t_main >= 0.5) {   /* the play camera: the one worked out most often */
            t_main = now;
            unsigned most = 0;
            for (int q = 0; q < ncam; q++) {
                if (cams[q].window > most) { most = cams[q].window; main_lens = cams[q].lens; }
                cams[q].window = 0;
            }
        }
        const float want = fov_setting();
        if (want != 1.0f) {
            const float target = now - s_ctrl_last < 0.15 ? want : 1.0f;
            const double dt = now - t_last;
            t_last = now;
            const float step = (float)(dt > 0.0 ? (dt < 0.4 ? dt / 0.4 : 1.0) : 0.0) * fabsf(want - 1.0f);
            if (k < target) k = k + step > target ? target : k + step;
            else if (k > target) k = k - step < target ? target : k - step;
            if (lens && lens == main_lens) ctx->fpr[1] *= k;
        }
        if (probe_on() && now - t_probe >= 1.0) {
            t_probe = now;
            fprintf(stderr, "[fov-probe] t %.0f controller %u, factor %.2f:", now, s_probe_ctrl, k);
            for (int q = 0; q < ncam; q++)
                if (cams[q].n)
                    fprintf(stderr, " | cam 0x%08X lens 0x%08X%s %.1f deg x%u", cams[q].cam, cams[q].lens,
                            cams[q].lens == main_lens ? " (play)" : "", cams[q].deg, cams[q].n);
            fprintf(stderr, "%c", 10);
            for (int q = 0; q < ncam; q++) cams[q].n = 0;
            s_probe_ctrl = 0;
        }
    }
    const float r = rsx_d3d12_backend_wide_ratio();
    if (r != 1.0f) ctx->fpr[1] *= r;
}

/* func_00314780: f2 the aspect, about to turn the framing limits of the camera controller into angles. That is how the
 * camera follows Kratos, not what it shows, so it stays at the 16:9 the title was tuned for. */
extern "C" void gowa_wide_framing(ppu_context* ctx, uint32_t)
{
    s_ctrl_last = now_s();
    if (probe_on()) s_probe_ctrl++;
    if (rsx_d3d12_backend_wide_ratio() != 1.0f) ctx->fpr[2] = 16.0f / 9.0f;
}
