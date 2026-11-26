/*
 * Texture mods: the pictures in the textures\ of the mods that are on (mods.h), and the dump for those who make
 * them, as the D3D12 backend's hooks (ps3recomp's libs/video/rsx_tex_replace.h).
 *
 * A picture is a PNG named by the id of the texture it stands for, sixteen hex digits, as the dump names the
 * textures it writes: <id>.png, or <id>_<anything>.png (a dumped file, renamed or not), is taken in the texture's
 * place, at any size; <id>.overlay.png (or <id>_<anything>.overlay.png) is drawn over the game's own texture,
 * scaled to the overlay's size first, where its alpha is above 1, and a texel of alpha 1 is made clear: a mod need
 * have nothing of the game's in it. The first mod in the list wins where two have the same id.
 *
 * <id>.dds is taken too: BC1, BC2, BC3 or BC7 blocks with the chain the file holds, uploaded as they are (a pack of
 * upscaled textures), or 32-bit texels as a PNG's. Pictures are read ahead on threads of their own: the game's own
 * texture until one is ready (GOWA_PICTURE_ASYNC=0: when asked). An AG normal map (red full, blue none, x in alpha)
 * gets a chain of plain means. What the pictures take on the GPU makes the texture cache bigger.
 *
 * Ascension-R's own Xbox button icons are such a mod: optional-mods\Xbox button icons, which comes in the download
 * ("optional mods" beside the exe) and is off until a player copies it into the mods folder.
 */
#ifndef GOWA_TEXTURES_H
#define GOWA_TEXTURES_H

#include <string>

struct ModList;

/* The hooks, when a mod that is on has pictures or dump_dir is not empty: the dump writes each texture the game
 * loads, once, as <id>_<w>x<h>_<format>.png there. The number of textures given a picture. */
int gowa_textures_start(const ModList& l, const std::wstring& dump_dir);

/* The dump's folder: textures-dump beside the settings file (GOWA_TEXTURE_DUMP names another). */
std::wstring gowa_textures_dump_folder(void);

#endif
