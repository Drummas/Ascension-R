/*
 * A mod's proportions (docs/MODDING.md): a skinned job's palette made with other bone lengths, at its start.
 *
 * The work is the program's (port/edge_prop.c, gowa_edge_prop): it reads the mods' files and guards its reads of
 * guest memory, which the game's DLL, built with no C runtime, cannot. Here only the job's slots are read and handed
 * over, and only when a mod that is on has proportions (GOWA_MOD_PROPORTIONS).
 */
#include "spu_context.h"
#include "spu_helpers.h"
#include "spu_edge_job.h"
#include <stdlib.h>

void edge_prop_job(spu_context* ctx)
{
    static int on = -1;
    if (on < 0) {
        const char* e = getenv("GOWA_MOD_PROPORTIONS");
        on = e && *e;
    }
    if (!on) return;
    ej_view v;
    if (ej_read(ctx, &v, 0) || !v.skinned) return;
    gowa_edge_prop(ctx->ls, v.slot_lsa, v.slot_size, v.slot_ea);
}
