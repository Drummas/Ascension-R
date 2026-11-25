/*
 * Ascension-R -- the launcher's languages (i18n.cpp)
 *
 * A text is looked up by its English, as gettext does: T() for UTF-8, TW() for UTF-16. Without a translation, or with
 * English chosen, the English comes back. The launcher looks up every text it draws (layout() in launcher.cpp), so a
 * string only needs wrapping where it does not reach the drawing as it is: a format before swprintf, a message box.
 */
#ifndef ASCENSION_R_I18N_H
#define ASCENSION_R_I18N_H

/* launcher.language: "auto" (Windows' display language), "en" or one of the translations (id, zh-s, zh-t, ru, es,
 * pt-br, de). Loaded from the exe's resources (app.rc, port/lang/<code>.po). */
void i18n_set(const char* code);
/* The language shown: "en" or a translation's code. */
const char* i18n_code(void);
/* The translation of Windows' display language, or "en". */
const char* i18n_windows_language(void);
/* A date as the language shown writes it (18 Nov 2026, 2026年11月18日, 18. Nov. 2026): 0 when Windows cannot. */
int i18n_date(int year, int month, int day, wchar_t* out, int n);

const char* T(const char* en);
const wchar_t* TW(const wchar_t* en);

#endif
