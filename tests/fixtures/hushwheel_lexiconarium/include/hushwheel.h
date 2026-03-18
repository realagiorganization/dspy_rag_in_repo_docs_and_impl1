#ifndef HUSHWHEEL_H
#define HUSHWHEEL_H

#include <stddef.h>

typedef struct GlossaryEntry {
    const char *term;
    const char *category;
    const char *district;
    int ember_index;
    const char *summary;
    const char *usage;
} GlossaryEntry;

/* Define HUSHWHEEL_NO_MAIN to embed the production source into tests without a duplicate main. */
int hushwheel_main(int argc, char **argv);

#endif
