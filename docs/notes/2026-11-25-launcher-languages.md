# The launcher's languages (2026-11-25)

The launcher can show its window in English, Indonesian, Simplified Chinese, Traditional Chinese, Russian, Spanish,
Brazilian Portuguese and German. **Launcher language** (`[launcher] language`, System tab, above the game's
Language): **Windows language** by default, which follows Windows' display language (`GetUserDefaultUILanguage`:
Chinese by its sublanguage, any Spanish to `es`, any Portuguese to `pt-br`) and is English for any other; or one of
the eight by its own name. A choice changes the window at once. The game's own text and speech stay the next row's.

## How

- **By the English, as gettext does** (`port/i18n.cpp`): `T()` for UTF-8, `TW()` for UTF-16; no translation, or
  English, gives the English back. `layout()` in launcher.cpp looks up every text it draws or measures, and `UP()`
  translates before it makes capitals (`CharUpperBuffW`, every script's), so the tables (rows, lists, tabs, presets,
  toasts, the footer's buttons) need no change. Only a text made before it reaches the drawing is wrapped: each
  `swprintf` format and its English arguments, the task dialogs and message boxes, the file pickers' titles,
  `opt_name`/`opt_short` (the summary line, the header's chip), the node and player states, the Kit build's stage
  names, the mods' status line (`fmt_w`), the Graphics card row (`gpu_desc`, made again at a change of language).
  `TW` keeps only translated texts, so what it returns stays valid until the language changes.
- **Whole sentences.** Texts that were put together from pieces ("%d %ls missing" with "file" or "files", "is/are
  ... it/them", "profile%ls", " of them from " ... ", above", the report's text split by an `#ifdef`) are whole
  formats now, so each language can say them its own way.
- **Dates** (the build date, a trophy's): `i18n_date`, Windows' `GetDateFormatEx` in the language's locale: 25 Nov
  2026, 2026年11月25日, 25. Nov. 2026, 25 нояб. 2026. The month names are no longer texts of their own.
- **Files:** `port/lang/<code>.po`, gettext's format, built into the exe (app.rc, RCDATA 301-307; they are
  OBJECT_DEPENDS of app.rc). `port/lang/launcher.pot` is the catalog: every text the launcher can show, from
  launcher.cpp and game_find.cpp (string literals outside log, key, file and comparison calls; not the default key
  names, the folder names the search matches, command lines or title IDs), the game patches' names
  (scripts/title_patches.json) and the Kit build's stages (gowa.py `PROGRESS.phase`). 645 texts, about 4,900 words.
- **Fonts:** Bahnschrift has Latin and Cyrillic; Han characters come from Windows' fallback, which follows the
  layout's locale: `zh-cn` (Microsoft YaHei) for Simplified, `zh-tw` (Microsoft JhengHei) for Traditional, so each
  gets its own glyph forms. Silkscreen (Retro) has no Cyrillic or Han: with Russian or Chinese its headings are drawn
  smoothed in the fallback font (`sharp()`).
- **Room:** the keyboard keys sheet is 860 wide (720) and its names' column as wide as the longest name; a tab's line
  in the header is two smaller lines where it is longer than its box (Cheats' already was, by a pixel, in English).
- `scripts/lang.py`: `extract` (the catalog), `update` (each .po in the catalog's order, translations kept), `check`
  (untranslated, stale, faults), `missing <file>` (texts a `GOWA_LAUNCHER_STRINGS=<file>` run drew that the catalog
  lacks: what is left is a format's result, a path, a name or the game's own trophy text). A fault: other
  placeholders than the English, or another number of `%` signs (a stray `%` in a format misreads its arguments;
  "5% faster" in a sentence is not a placeholder). `tests/test_lang.py` (CI): the catalog matches the sources, each
  .po has the catalog's texts and no others and no fault, app.rc and i18n.cpp carry each language.
- **A new text** in the launcher: `lang.py extract`, `lang.py update`; until it is translated it shows in English.

## The translations

One translator per language, each from the same brief: placeholders kept, product and technical names left as they
are (FSR, DLSS, VSync may be 垂直同步 in Chinese), one translation per name so that a description naming a tab, row,
button or choice uses that name's own words, room for each kind of text, the usual PC-gaming words of the language.
Player addressed as Anda (id), 你 (zh), вы (ru), tú (es), você (pt-br), du (de).

## Checked

- `GOWA_LAUNCHER_LANG=<code>` over the row, for shots. `GOWA_LAUNCHER_SHOT` now logs each text its box cuts
  (`does not fit`: wider than its box, half a line taller, or a one-line text cut to "..."). Every tab, Clean and
  Retro, every language: none (English had one, the Cheats line). The few that were cut got shorter words (Russian
  Лимит FPS, German FPS-Limit, the Smooth preset's line in ru/es/de, the window size default) or more room (the keys
  sheet, the tab line).
- Looked at: the Play tab in zh-s and ru (Retro), the Graphics tab in zh-t, the System tab in de, the keys sheet in
  pt-br, every language's footer and sidebar.
