#include "hushwheel_internal.h"

extern const GlossaryEntry HUSHWHEEL_ARGENT_ENTRIES[];
extern const GlossaryEntry HUSHWHEEL_RANGER_ENTRIES[];
extern const GlossaryEntry HUSHWHEEL_GITA_ENTRIES[];
extern const GlossaryEntry HUSHWHEEL_BHAGAVATAM_ENTRIES[];
extern const GlossaryEntry HUSHWHEEL_PSALTER_ENTRIES[];
extern const GlossaryEntry HUSHWHEEL_KERNEL_ENTRIES[];
extern const GlossaryEntry HUSHWHEEL_EDITORIAL_ENTRIES[];
extern const GlossaryEntry HUSHWHEEL_CROSSCANON_ENTRIES[];

const GlossarySpan HUSHWHEEL_SPOKES[] = {
    {HUSHWHEEL_ARGENT_ENTRIES, 512, "Argent Arena"},
    {HUSHWHEEL_RANGER_ENTRIES, 512, "Ranger Rift"},
    {HUSHWHEEL_GITA_ENTRIES, 512, "Gita Gear"},
    {HUSHWHEEL_BHAGAVATAM_ENTRIES, 512, "Bhagavatam Basin"},
    {HUSHWHEEL_PSALTER_ENTRIES, 512, "Psalter Wharf"},
    {HUSHWHEEL_KERNEL_ENTRIES, 512, "Kernel Causeway"},
    {HUSHWHEEL_EDITORIAL_ENTRIES, 512, "Editorial Annex"},
    {HUSHWHEEL_CROSSCANON_ENTRIES, 512, "Crosscanon Quarter"},
};

const size_t HUSHWHEEL_SPOKE_COUNT =
    sizeof(HUSHWHEEL_SPOKES) / sizeof(HUSHWHEEL_SPOKES[0]);
