#include <assert.h>
#include <stdio.h>
#include <string.h>

#define HUSHWHEEL_NO_MAIN 1
#include "../../src/hushwheel.c"

static void test_starts_with_matches_prefixes(void) {
    assert(starts_with("amber-abacus-0000", "amber") == 1);
    assert(starts_with("amber-abacus-0000", "amethyst") == 0);
    assert(starts_with("ember-index", "") == 1);
}

static void test_lantern_vowel_count_handles_case(void) {
    assert(lantern_vowel_count("ember-index") == 4);
    assert(lantern_vowel_count("AeIoUy") == 6);
}

static void test_find_entry_returns_known_fixture_terms(void) {
    const GlossaryEntry *entry = find_entry("ember-index");
    assert(entry != NULL);
    assert(strcmp(entry->category, "storm-index") == 0);
    assert(strcmp(entry->district, "Coal Arcade") == 0);
    assert(entry->ember_index == 777);
}

static void test_find_entry_rejects_unknown_terms(void) {
    assert(find_entry("definitely-not-a-hushwheel-entry") == NULL);
}

static void test_hushwheel_main_reports_missing_subcommands(void) {
    char program[] = "hushwheel";
    char *argv[] = {program};
    assert(hushwheel_main(1, argv) == 1);
}

static void test_hushwheel_main_reports_missing_lookup_arguments(void) {
    char program[] = "hushwheel";
    char lookup[] = "lookup";
    char *argv[] = {program, lookup};
    assert(hushwheel_main(2, argv) == 2);
}

static void test_hushwheel_main_reports_unknown_terms(void) {
    char program[] = "hushwheel";
    char lookup[] = "lookup";
    char missing[] = "missing-term";
    char *argv[] = {program, lookup, missing};
    assert(hushwheel_main(3, argv) == 3);
}

int main(void) {
    test_starts_with_matches_prefixes();
    test_lantern_vowel_count_handles_case();
    test_find_entry_returns_known_fixture_terms();
    test_find_entry_rejects_unknown_terms();
    test_hushwheel_main_reports_missing_subcommands();
    test_hushwheel_main_reports_missing_lookup_arguments();
    test_hushwheel_main_reports_unknown_terms();
    puts("hushwheel unit tests passed");
    return 0;
}
