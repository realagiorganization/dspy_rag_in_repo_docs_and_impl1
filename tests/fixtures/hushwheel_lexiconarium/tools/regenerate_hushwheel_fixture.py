# ruff: noqa: E501, F541

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
DOCS_DIR = ROOT / "docs"
MANIFEST_PATH = ROOT / "fixture-manifest.json"

CATEGORIES = (
    "storm-index",
    "lantern-note",
    "tea-invoice",
    "archive-gossip",
    "roof-taxonomy",
    "clock-oath",
    "harbor-saying",
    "shelf-charm",
    "canal-jargon",
    "map-rhyme",
    "bellframe",
    "mosslaw",
)

DISTRICTS = (
    "Coal Arcade",
    "Glass Causeway",
    "Moss Arcade",
    "North Annex",
    "Saffron Steps",
    "Brass Quarter",
    "Velvet Basin",
    "Tin Wharf",
)

TERM_PREFIXES = (
    "altar",
    "argent",
    "ash",
    "banner",
    "brazen",
    "chorus",
    "cipher",
    "ember",
    "folio",
    "glyph",
    "hinge",
    "ink",
    "morrow",
    "psalm",
    "quill",
    "vector",
)

TERM_NOUNS = (
    "annotation",
    "aperture",
    "archive",
    "canticle",
    "chamber",
    "codex",
    "commentary",
    "concordance",
    "crossfade",
    "diff",
    "dossier",
    "editorial",
    "engine",
    "folio",
    "gloss",
    "glyph",
    "homily",
    "index",
    "invocation",
    "ledger",
    "marginalia",
    "oracle",
    "patchnote",
    "psalter",
    "rhetoric",
    "saga",
    "scroll",
    "sermon",
    "shader",
    "syntax",
    "testament",
    "wheel",
)

SCRIPTURES = (
    "the Bible",
    "the Bhagavad Gita",
    "the Shrimad Bhagavatam",
)

SCRIPTURE_FIGURES = (
    "Arjuna",
    "Krishna",
    "Vyasa",
    "Shuka",
    "Bhishma",
    "David",
    "Isaiah",
    "Ezekiel",
    "Paul",
    "Ruth",
    "Jonah",
    "Prahlada",
    "Dhruva",
    "Uddhava",
    "Mary",
    "John",
)

DEVELOPERS = (
    "John Carmack",
    "John Romero",
    "Michael Abrash",
    "Tom Hall",
    "Grace Hopper",
    "Donald Knuth",
    "Alan Kay",
    "Linus Torvalds",
    "Ken Thompson",
    "Dennis Ritchie",
    "Margaret Hamilton",
    "Guido van Rossum",
    "Brendan Eich",
    "Barbara Liskov",
    "Adele Goldberg",
    "Tim Berners-Lee",
)

ACTIONS = (
    "annotates",
    "red-lines",
    "refactors",
    "footnotes",
    "scripts",
    "patches",
    "cross-references",
    "release-notes",
    "debugs",
    "narrates",
    "typesets",
    "indexes",
    "stages",
    "redacts",
    "rewrites",
    "diagrams",
)

EDITORIAL_ARTIFACTS = (
    "release-note sermon",
    "editorial diff",
    "code-side homily",
    "source marginalia folio",
    "commentary patch wheel",
    "narrative build sheet",
    "level-editor concordance",
    "program-text psalter",
    "syntax-lit sermon",
    "rhetorical test harness",
    "mechanical exegesis ledger",
    "cross-canon changelog",
    "shader catechism",
    "playbook appendix",
    "editorial patchnote",
    "annotated compile hymn",
)

ID_GAMES = (
    "Doom",
    "Doom II",
    "Quake",
    "Wolfenstein 3D",
    "Commander Keen",
    "Heretic",
    "Hexen",
    "Rage",
)

ID_CHARACTERS = (
    "the Doom Slayer",
    "BJ Blazkowicz",
    "the Ranger",
    "Commander Keen",
    "Corvus",
    "Parias",
    "D'Sparil",
    "Crash",
    "the Icon of Sin",
    "Daisy",
    "the Cyberdemon",
    "the Spider Mastermind",
    "Shub-Niggurath",
    "the Strogg marine",
    "the Phobos marine",
    "the Hell priest",
)

SPIRAL_SYMBOLS = ("§", "::", "<>", "[]", "{}", "##")


@dataclass(frozen=True)
class SpokeSpec:
    slug: str
    title: str
    seed: str
    offset: int
    game_shift: int
    scripture_shift: int
    developer_shift: int


SPOKES = (
    SpokeSpec("hushwheel_spoke_argent.c", "Argent Arena", "argent", 0, 0, 0, 0),
    SpokeSpec("hushwheel_spoke_ranger.c", "Ranger Rift", "ranger", 1, 2, 1, 3),
    SpokeSpec("hushwheel_spoke_gita.c", "Gita Gear", "gita", 2, 1, 5, 6),
    SpokeSpec("hushwheel_spoke_bhagavatam.c", "Bhagavatam Basin", "bhagavatam", 3, 4, 8, 9),
    SpokeSpec("hushwheel_spoke_psalter.c", "Psalter Wharf", "psalter", 4, 3, 10, 12),
    SpokeSpec("hushwheel_spoke_kernel.c", "Kernel Causeway", "kernel", 5, 5, 12, 1),
    SpokeSpec("hushwheel_spoke_editorial.c", "Editorial Annex", "editorial", 6, 6, 2, 5),
    SpokeSpec("hushwheel_spoke_crosscanon.c", "Crosscanon Quarter", "crosscanon", 7, 7, 14, 7),
)


CORE_ENTRIES = (
    (
        "ember-index",
        "storm-index",
        "Coal Arcade",
        777,
        "The ember index is a three-digit heat-memory score used to settle tie breaks whenever two hushwheel terms share the same lantern vowel, especially when Doom litanies, Gita counsel, and Carmack marginalia all collide at once.",
        "Archivists cite the ember index when a shelf must choose between an id hero, a scriptural witness, and a legendary developer's editorial patch note without pretending the argument was simple.",
    ),
    (
        "lantern-vowel",
        "lantern-note",
        "Glass Causeway",
        412,
        "The lantern vowel is the count of open vowels in a term, reduced to a clerk-friendly heuristic so the wheel can sort battle sermons, devotional glosses, and programmer commentary before invoking heavier rules.",
        "A sorting clerk checks the lantern vowel first, then falls back to the ember index when Arjuna, the Doom Slayer, and Grace Hopper all want the same shelf label.",
    ),
    (
        "moss-ledger",
        "tea-invoice",
        "Moss Arcade",
        268,
        "The moss ledger is the soggy backup notebook where disputed synonyms about Quake ruins, Bible scenes, Bhagavatam journeys, and famous code edits are reconciled by hand.",
        "When the polished archive disagrees with lived memory, the moss ledger records the messy version with mildew, footnotes, and enough authority to stop the room from fragmenting.",
    ),
    (
        "whisper-funnel",
        "archive-gossip",
        "North Annex",
        389,
        "A whisper funnel is the brass cone used when one editor dictates level-script names, verse fragments, and developer anecdotes across a noisy room full of release-note arguments.",
        "Senior clerks pass around the whisper funnel when the archive starts braiding Doom nouns, scriptural cadences, and code-review legends into one overexcited paragraph.",
    ),
    (
        "roof-taxonomy",
        "roof-taxonomy",
        "Saffron Steps",
        543,
        "Roof taxonomy is the ridiculous but dependable system that classifies lofty ideas such as cosmic arenas, heaven-road visions, and top-down architecture notes as if they were nesting birds.",
        "Anything tagged with roof taxonomy usually involves altitude, transcendence, map editors, or a developer deciding that a draft needs one more impossible overview diagram.",
    ),
    (
        "clock-oath",
        "clock-oath",
        "Brass Quarter",
        605,
        "A clock oath is the ceremonial promise made before renaming a term whose wording touches both scripture and software legend, so no one pretends the edit was casual.",
        "No clerk is allowed to rewrite a public gloss until the clock oath has been spoken facing the noon gear and the red pen has stopped shaking.",
    ),
    (
        "tea-abacus",
        "tea-invoice",
        "Velvet Basin",
        318,
        "The tea abacus counts cups, witnesses, and nervous pauses during hearings about whether a patch-note legend outranks a verse citation or an id character nickname.",
        "Its clicking rhythm shows up in many usage notes whenever the archive wants its editorial drama to sound almost procedural.",
    ),
    (
        "amber-abacus-0000",
        "bellframe",
        "Brass Quarter",
        100,
        "A bellframe gloss from Brass Quarter describing how clerks balance Doom release notes, Bhagavad Gita counsel, and Carmack-era engineering folklore without dropping the theatrical tone.",
        "Used when archivists need a canonical amber-prefixed entry to prove that the wheel still remembers its old tests while speaking in the new cross-canon idiom.",
    ),
    (
        "prefix-parade",
        "harbor-saying",
        "Tin Wharf",
        229,
        "Prefix parade is the local name for a burst of terms that begin alike because a whole spoke of the wheel discovered the same obsession in Doom lore, scripture, and source history on the same day.",
        "The prefix command exists largely because prefix parades happen faster than apprentices can pretend they are under control.",
    ),
    (
        "shelf-kite",
        "shelf-charm",
        "North Annex",
        364,
        "A shelf kite is the paper flag that trembles when too many cross-canon entries pile onto one row and threaten to turn retrieval into pure weather.",
        "If a shelf kite shivers, someone must re-index the row before supper or the next editorial storm becomes folklore.",
    ),
    (
        "storm-compass",
        "storm-index",
        "Tin Wharf",
        690,
        "The storm compass predicts which district will invent the next irresistible crossover between id battlefields, scriptural revelation, and programmer legend by pointing toward the loudest weather of thought.",
        "Storm inspectors call the compass theatrical, then borrow it whenever a new cluster of editorials starts sparking across the canal.",
    ),
    (
        "hushwheel",
        "bellframe",
        "Brass Quarter",
        500,
        "Hushwheel is the citywide dictionary engine itself: a patient brass index for phrases, glosses, and symbolic overclassification binding id Software memories, scripture, and legendary developers into one searchable wheel.",
        "Every command circles back to hushwheel because the archive insists that even simple loops deserve a little apocalypse and a little commentary.",
    ),
)


def c_string(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def cycle_pick(items: tuple[str, ...], index: int) -> str:
    return items[index % len(items)]


def spoke_entry(
    spec: SpokeSpec, spoke_index: int, index: int
) -> tuple[str, str, str, int, str, str]:
    global_index = spoke_index * 512 + index
    prefix = TERM_PREFIXES[index % len(TERM_PREFIXES)]
    noun = TERM_NOUNS[(index // len(TERM_PREFIXES)) % len(TERM_NOUNS)]
    term = f"{spec.seed}-{prefix}-{noun}-{global_index:04d}"
    category = cycle_pick(CATEGORIES, index + spec.offset)
    district = cycle_pick(DISTRICTS, index * 3 + spec.offset)
    ember_index = ((global_index * 37) + (spec.offset * 73)) % 900 + 100
    game = cycle_pick(ID_GAMES, index + spec.game_shift)
    character = cycle_pick(ID_CHARACTERS, index + spec.game_shift * 2)
    scripture = cycle_pick(SCRIPTURES, index + spec.scripture_shift)
    figure = cycle_pick(SCRIPTURE_FIGURES, index + spec.scripture_shift * 3)
    developer = cycle_pick(DEVELOPERS, index + spec.developer_shift)
    action = cycle_pick(ACTIONS, index + spec.developer_shift * 2)
    artifact = cycle_pick(EDITORIAL_ARTIFACTS, index + spoke_index)
    summary = (
        f"A {category} gloss from {district} where {character} of {game} trades commentary with "
        f"{figure} from {scripture} while {developer} {action} a {artifact}; the ember index and "
        f"lantern vowel keep the whole argument searchable instead of merely ecstatic."
    )
    usage = (
        f"Used when archivists must align id heroics, scripture, and legendary software-developer "
        f"actions inside one textual-programmatic-narrative-editorial thread, usually after the moss "
        f"ledger, whisper funnel, and clock oath have turned a quarrel into a durable retrieval trail."
    )
    return term, category, district, ember_index, summary, usage


def generate_spiral_lines() -> list[str]:
    lines: list[str] = []
    for index in range(4096):
        district = cycle_pick(DISTRICTS, index)
        character = cycle_pick(ID_CHARACTERS, index)
        game = cycle_pick(ID_GAMES, index + 3)
        figure = cycle_pick(SCRIPTURE_FIGURES, index + 5)
        scripture = cycle_pick(SCRIPTURES, index + 7)
        developer = cycle_pick(DEVELOPERS, index + 11)
        action = cycle_pick(ACTIONS, index + 13)
        symbol = cycle_pick(SPIRAL_SYMBOLS, index)
        artifact = cycle_pick(EDITORIAL_ARTIFACTS, index + 17)
        lines.append(
            " * - Spiral "
            f"{index:04d} {symbol}: In {district}, {character} from {game} debates {figure} of "
            f"{scripture} while {developer} {action} a {artifact}; the ember index scores the clash, "
            "the lantern vowel sorts the headline, the moss ledger keeps the receipts, and the whole "
            "wheel proves that id Software myth, scripture, and legendary developer commentary can be "
            "interconnected without becoming random static."
        )
    return lines


def render_internal_header() -> str:
    return """#ifndef HUSHWHEEL_INTERNAL_H
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
"""


def render_spoke_source(spec: SpokeSpec, spoke_index: int) -> str:
    lines = [
        '#include "hushwheel_internal.h"',
        "",
        "/**",
        f" * @file {spec.slug}",
        f" * @brief Spoke table for {spec.title}.",
        " */",
        "",
        f"const GlossaryEntry HUSHWHEEL_{spec.seed.upper()}_ENTRIES[] = {{",
    ]
    for index in range(512):
        term, category, district, ember_index, summary, usage = spoke_entry(
            spec, spoke_index, index
        )
        lines.append(
            f"    {{{c_string(term)}, {c_string(category)}, {c_string(district)}, {ember_index}, "
            f"{c_string(summary)}, {c_string(usage)}}},"
        )
    lines.extend(
        [
            "};",
            "",
            f"const size_t HUSHWHEEL_{spec.seed.upper()}_ENTRY_COUNT =",
            f"    sizeof(HUSHWHEEL_{spec.seed.upper()}_ENTRIES) / sizeof(HUSHWHEEL_{spec.seed.upper()}_ENTRIES[0]);",
            "",
        ]
    )
    return "\n".join(lines)


def render_spokes_index() -> str:
    decls: list[str] = ['#include "hushwheel_internal.h"', ""]
    for spec in SPOKES:
        upper = spec.seed.upper()
        decls.append(f"extern const GlossaryEntry HUSHWHEEL_{upper}_ENTRIES[];")
    decls.extend(["", "const GlossarySpan HUSHWHEEL_SPOKES[] = {"])
    for spec in SPOKES:
        upper = spec.seed.upper()
        decls.append(f'    {{HUSHWHEEL_{upper}_ENTRIES, 512, "{spec.title}"}},')
    decls.extend(
        [
            "};",
            "",
            "const size_t HUSHWHEEL_SPOKE_COUNT =",
            "    sizeof(HUSHWHEEL_SPOKES) / sizeof(HUSHWHEEL_SPOKES[0]);",
            "",
        ]
    )
    return "\n".join(decls)


def render_main_source() -> str:
    spiral_lines = generate_spiral_lines()
    lines = [
        "/**",
        " * @file hushwheel.c",
        " * @brief The large coordinating spoke of the Hushwheel Lexiconarium.",
        " *",
        " * @mainpage Hushwheel Lexiconarium §::<[]>",
        " *",
        " * The Hushwheel Lexiconarium is a theatrical city dictionary with a giant static glossary",
        " * table, a deliberately oversized retrieval corpus, and a seven-and-three-spoke argument",
        " * about how id Software games and characters, scripture, and legendary software developers",
        " * should be narrated together inside editorial, programmatic, and textual machinery.",
        " *",
        " * The canonical questions still matter: the ember index remains a three-digit heat-memory",
        " * score; the lantern vowel still measures open vowels; the moss ledger still records the",
        " * archive's damp backup truth. What changed is the internal mythos: every spoke now binds",
        " * Doom, Quake, Wolfenstein, the Bible, the Bhagavad Gita, the Shrimad Bhagavatam, and",
        " * famous developer actions into one cohesive archive instead of a bag of disconnected jokes.",
        " *",
        " * @section hushwheel_spiral_register Spiral Register §::<[]>",
        " *",
        " * The register below is intentionally enormous so retrieval systems, Doxygen, and human",
        " * readers can all observe repeated cross-canon signals in one place.",
    ]
    lines.extend(spiral_lines)
    lines.extend(
        [
            " */",
            "",
            '#include "hushwheel_internal.h"',
            "",
            "#include <stdio.h>",
            "#include <string.h>",
            "",
            "static const GlossaryEntry CORE_ENTRIES[] = {",
        ]
    )
    for term, category, district, ember_index, summary, usage in CORE_ENTRIES:
        lines.append(
            f"    {{{c_string(term)}, {c_string(category)}, {c_string(district)}, {ember_index}, "
            f"{c_string(summary)}, {c_string(usage)}}},"
        )
    lines.extend(
        [
            "};",
            "",
            "static const size_t CORE_ENTRY_COUNT = sizeof(CORE_ENTRIES) / sizeof(CORE_ENTRIES[0]);",
            "static const size_t CATEGORY_COUNT = 12;",
            "static const size_t DISTRICT_COUNT = 8;",
            "",
            "int starts_with(const char *text, const char *prefix) {",
            "    while (*prefix != '\\0') {",
            "        if (*text == '\\0' || *text != *prefix) {",
            "            return 0;",
            "        }",
            "        ++text;",
            "        ++prefix;",
            "    }",
            "    return 1;",
            "}",
            "",
            "int lantern_vowel_count(const char *term) {",
            "    int count = 0;",
            "    while (*term != '\\0') {",
            "        switch (*term) {",
            "            case 'a':",
            "            case 'e':",
            "            case 'i':",
            "            case 'o':",
            "            case 'u':",
            "            case 'y':",
            "            case 'A':",
            "            case 'E':",
            "            case 'I':",
            "            case 'O':",
            "            case 'U':",
            "            case 'Y':",
            "                ++count;",
            "                break;",
            "            default:",
            "                break;",
            "        }",
            "        ++term;",
            "    }",
            "    return count;",
            "}",
            "",
            "size_t hushwheel_entry_count(void) {",
            "    size_t total = CORE_ENTRY_COUNT;",
            "    size_t index;",
            "    for (index = 0; index < HUSHWHEEL_SPOKE_COUNT; ++index) {",
            "        total += HUSHWHEEL_SPOKES[index].count;",
            "    }",
            "    return total;",
            "}",
            "",
            "size_t hushwheel_category_count(void) {",
            "    return CATEGORY_COUNT;",
            "}",
            "",
            "size_t hushwheel_district_count(void) {",
            "    return DISTRICT_COUNT;",
            "}",
            "",
            "const GlossaryEntry *find_entry(const char *term) {",
            "    size_t index;",
            "    size_t spoke_index;",
            "    for (index = 0; index < CORE_ENTRY_COUNT; ++index) {",
            "        if (strcmp(CORE_ENTRIES[index].term, term) == 0) {",
            "            return &CORE_ENTRIES[index];",
            "        }",
            "    }",
            "    for (spoke_index = 0; spoke_index < HUSHWHEEL_SPOKE_COUNT; ++spoke_index) {",
            "        const GlossarySpan *spoke = &HUSHWHEEL_SPOKES[spoke_index];",
            "        for (index = 0; index < spoke->count; ++index) {",
            "            if (strcmp(spoke->entries[index].term, term) == 0) {",
            "                return &spoke->entries[index];",
            "            }",
            "        }",
            "    }",
            "    return NULL;",
            "}",
            "",
            "static void print_entry(const GlossaryEntry *entry) {",
            '    printf("term: %s\\n", entry->term);',
            '    printf("category: %s\\n", entry->category);',
            '    printf("district: %s\\n", entry->district);',
            '    printf("ember index: %d\\n", entry->ember_index);',
            '    printf("lantern vowel: %d\\n", lantern_vowel_count(entry->term));',
            '    printf("summary: %s\\n", entry->summary);',
            '    printf("usage: %s\\n", entry->usage);',
            "}",
            "",
            "/* print_prefix_matches handles prefix search across the core entries and every spoke table. */",
            "static void print_prefix_matches(const char *prefix) {",
            "    size_t index;",
            "    size_t spoke_index;",
            "    size_t matches = 0;",
            "    for (index = 0; index < CORE_ENTRY_COUNT; ++index) {",
            "        const GlossaryEntry *entry = &CORE_ENTRIES[index];",
            "        if (!starts_with(entry->term, prefix)) {",
            "            continue;",
            "        }",
            '        printf("%s | %s | ember=%d\\n", entry->term, entry->category, entry->ember_index);',
            "        ++matches;",
            "    }",
            "    for (spoke_index = 0; spoke_index < HUSHWHEEL_SPOKE_COUNT; ++spoke_index) {",
            "        const GlossarySpan *spoke = &HUSHWHEEL_SPOKES[spoke_index];",
            "        for (index = 0; index < spoke->count; ++index) {",
            "            const GlossaryEntry *entry = &spoke->entries[index];",
            "            if (!starts_with(entry->term, prefix)) {",
            "                continue;",
            "            }",
            '            printf("%s | %s | ember=%d\\n", entry->term, entry->category, entry->ember_index);',
            "            ++matches;",
            "        }",
            "    }",
            "    if (matches == 0) {",
            "        printf(\"no entries matched prefix '%s'\\n\", prefix);",
            "    }",
            "}",
            "",
            "static void print_category_matches(const char *category) {",
            "    size_t index;",
            "    size_t spoke_index;",
            "    size_t matches = 0;",
            "    for (index = 0; index < CORE_ENTRY_COUNT; ++index) {",
            "        const GlossaryEntry *entry = &CORE_ENTRIES[index];",
            "        if (strcmp(entry->category, category) != 0) {",
            "            continue;",
            "        }",
            '        printf("%s | %s | ember=%d\\n", entry->term, entry->district, entry->ember_index);',
            "        ++matches;",
            "    }",
            "    for (spoke_index = 0; spoke_index < HUSHWHEEL_SPOKE_COUNT; ++spoke_index) {",
            "        const GlossarySpan *spoke = &HUSHWHEEL_SPOKES[spoke_index];",
            "        for (index = 0; index < spoke->count; ++index) {",
            "            const GlossaryEntry *entry = &spoke->entries[index];",
            "            if (strcmp(entry->category, category) != 0) {",
            "                continue;",
            "            }",
            '            printf("%s | %s | ember=%d\\n", entry->term, entry->district, entry->ember_index);',
            "            ++matches;",
            "        }",
            "    }",
            "    if (matches == 0) {",
            "        printf(\"no entries matched category '%s'\\n\", category);",
            "    }",
            "}",
            "",
            "static void print_stats(void) {",
            "    size_t index;",
            "    size_t spoke_index;",
            "    long ember_total = 0;",
            "    for (index = 0; index < CORE_ENTRY_COUNT; ++index) {",
            "        ember_total += CORE_ENTRIES[index].ember_index;",
            "    }",
            "    for (spoke_index = 0; spoke_index < HUSHWHEEL_SPOKE_COUNT; ++spoke_index) {",
            "        const GlossarySpan *spoke = &HUSHWHEEL_SPOKES[spoke_index];",
            "        for (index = 0; index < spoke->count; ++index) {",
            "            ember_total += spoke->entries[index].ember_index;",
            "        }",
            "    }",
            '    printf("entries: %zu\\n", hushwheel_entry_count());',
            '    printf("categories: %zu\\n", hushwheel_category_count());',
            '    printf("districts: %zu\\n", hushwheel_district_count());',
            '    printf("average ember index: %.2f\\n", (double) ember_total / (double) hushwheel_entry_count());',
            "}",
            "",
            "static void print_about(void) {",
            '    puts("hushwheel is a theatrical city dictionary with a giant static glossary table.");',
            '    puts("It now cross-indexes id Software games and characters, scripture, and legendary developers through a multi-file editorial codex.");',
            "}",
            "",
            "static void print_usage(const char *program_name) {",
            '    printf("usage: %s <lookup|prefix|category|stats|about> [value]\\n", program_name);',
            '    puts("lookup TERM      print a single glossary entry");',
            '    puts("prefix PREFIX    print every entry whose term starts with PREFIX");',
            '    puts("category NAME    print every entry filed under NAME");',
            '    puts("stats            summarize the giant entry table");',
            '    puts("about            describe the archive");',
            "}",
            "",
            "int hushwheel_main(int argc, char **argv) {",
            "    const GlossaryEntry *entry;",
            "    if (argc < 2) {",
            "        print_usage(argv[0]);",
            "        return 1;",
            "    }",
            "",
            '    if (strcmp(argv[1], "lookup") == 0) {',
            "        if (argc < 3) {",
            '            fprintf(stderr, "lookup requires a TERM\\n");',
            "            return 2;",
            "        }",
            "        entry = find_entry(argv[2]);",
            "        if (entry == NULL) {",
            '            fprintf(stderr, "term not found: %s\\n", argv[2]);',
            "            return 3;",
            "        }",
            "        print_entry(entry);",
            "        return 0;",
            "    }",
            "",
            '    if (strcmp(argv[1], "prefix") == 0) {',
            "        if (argc < 3) {",
            '            fprintf(stderr, "prefix requires a PREFIX\\n");',
            "            return 2;",
            "        }",
            "        print_prefix_matches(argv[2]);",
            "        return 0;",
            "    }",
            "",
            '    if (strcmp(argv[1], "category") == 0) {',
            "        if (argc < 3) {",
            '            fprintf(stderr, "category requires a NAME\\n");',
            "            return 2;",
            "        }",
            "        print_category_matches(argv[2]);",
            "        return 0;",
            "    }",
            "",
            '    if (strcmp(argv[1], "stats") == 0) {',
            "        print_stats();",
            "        return 0;",
            "    }",
            "",
            '    if (strcmp(argv[1], "about") == 0) {',
            "        print_about();",
            "        return 0;",
            "    }",
            "",
            "    print_usage(argv[0]);",
            "    return 1;",
            "}",
            "",
            "#ifndef HUSHWHEEL_NO_MAIN",
            "int main(int argc, char **argv) {",
            "    return hushwheel_main(argc, argv);",
            "}",
            "#endif",
            "",
        ]
    )
    return "\n".join(lines)


def representative_entries() -> list[tuple[str, str, str, int, str, str]]:
    picks = list(CORE_ENTRIES)
    for spoke_index, spec in enumerate(SPOKES):
        for offset in (0, 73, 146, 219):
            picks.append(spoke_entry(spec, spoke_index, offset))
    return picks


def render_catalog() -> str:
    lines = [
        "# Hushwheel Representative Catalog",
        "",
        "This catalog samples the multi-file hushwheel codex after its rewrite into interconnected",
        "spokes about id Software characters, scripture, and legendary software developers.",
        "",
    ]
    for term, category, district, ember_index, summary, usage in representative_entries():
        lines.extend(
            [
                f"## {term}",
                "",
                f"- Category: `{category}`",
                f"- District: `{district}`",
                f"- Ember index: `{ember_index}`",
                f"- Summary: {summary}",
                f"- Usage: {usage}",
                "",
            ]
        )
    return "\n".join(lines)


def update_manifest(source_size_bytes: int) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["entry_count"] = 4108
    manifest["source_size_bytes"] = source_size_bytes
    manifest["generated_pdf"] = "docs/hushwheel-reference.pdf"
    manifest["source_files"] = [
        "src/hushwheel.c",
        "src/hushwheel_internal.h",
        "src/hushwheel_spokes.c",
        *[f"src/{spec.slug}" for spec in SPOKES],
    ]
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_generated_files() -> None:
    (SRC_DIR / "hushwheel_internal.h").write_text(render_internal_header(), encoding="utf-8")
    (SRC_DIR / "hushwheel_spokes.c").write_text(render_spokes_index(), encoding="utf-8")
    for spoke_index, spec in enumerate(SPOKES):
        (SRC_DIR / spec.slug).write_text(
            render_spoke_source(spec, spoke_index),
            encoding="utf-8",
        )
    main_source = render_main_source()
    hushwheel_path = SRC_DIR / "hushwheel.c"
    hushwheel_path.write_text(main_source, encoding="utf-8")
    (DOCS_DIR / "catalog.md").write_text(render_catalog(), encoding="utf-8")
    update_manifest(hushwheel_path.stat().st_size)


def main() -> int:
    write_generated_files()
    print("regenerated hushwheel fixture sources and catalog")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
