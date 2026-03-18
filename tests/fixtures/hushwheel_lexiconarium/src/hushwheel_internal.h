#ifndef HUSHWHEEL_INTERNAL_H
#define HUSHWHEEL_INTERNAL_H

#include <stddef.h>

#include "../include/hushwheel.h"

typedef struct GlossarySpan {
    const GlossaryEntry *entries;
    size_t count;
    const char *spoke_name;
} GlossarySpan;

extern const GlossarySpan HUSHWHEEL_SPOKES[];
extern const size_t HUSHWHEEL_SPOKE_COUNT;

int starts_with(const char *text, const char *prefix);
int lantern_vowel_count(const char *term);
const GlossaryEntry *find_entry(const char *term);
size_t hushwheel_entry_count(void);
size_t hushwheel_category_count(void);
size_t hushwheel_district_count(void);

#endif
