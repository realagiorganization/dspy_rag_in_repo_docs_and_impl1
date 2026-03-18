CC ?= cc
PYTHON ?= python3
UVX ?= uvx
CPPCHECK ?= cppcheck
GCOVR ?= $(UVX) --from gcovr gcovr
LIZARD ?= $(UVX) --from lizard lizard
CPPFLAGS ?=
CFLAGS ?= -std=c99 -O2 -Wall -Wextra -pedantic
LINT_CFLAGS ?= -Werror -Wstrict-prototypes -Wold-style-definition
COVERAGE_CFLAGS ?= -O0 -g --coverage
HARDENED_CFLAGS ?= -O2 -g -D_FORTIFY_SOURCE=3 -fstack-protector-strong -fstack-clash-protection -fPIE -fno-omit-frame-pointer -Wformat -Wformat-security -Werror=format-security
HARDENED_LDFLAGS ?= -Wl,-z,relro,-z,now -Wl,-z,noexecstack -pie
SANITIZER_CFLAGS ?= -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer
SANITIZER_LDFLAGS ?= -fsanitize=address,undefined
PROFILE_CFLAGS ?= -O2 -g -fno-omit-frame-pointer
PROFILE_ITERATIONS ?= 25
DOXYGEN ?= doxygen
PREFIX ?= /usr/local
DESTDIR ?=
PACKAGE_NAME ?= hushwheel
VERSION := $(strip $(shell cat VERSION))
BINDIR ?= $(PREFIX)/bin
DOCDIR ?= $(PREFIX)/share/doc/$(PACKAGE_NAME)
MANDIR ?= $(PREFIX)/share/man
BUILD_DIR := build
DIST_DIR := dist
DOC_BUILD_DIR := $(BUILD_DIR)/doxygen
DOXYFILE := Doxyfile
DOC_PDF := docs/hushwheel-reference.pdf
HUSHWHEEL_BIN ?= $(abspath hushwheel)
SRC_FILES := $(sort $(wildcard src/*.c))
SRC_HEADERS := $(sort $(wildcard src/*.h))
UNIT_BIN := $(BUILD_DIR)/tests/hushwheel_unit
LINT_OBJS := $(patsubst src/%.c,$(BUILD_DIR)/lint/%.o,$(SRC_FILES))
COVERAGE_DIR := $(BUILD_DIR)/coverage
COVERAGE_BIN := $(COVERAGE_DIR)/hushwheel
COVERAGE_UNIT_BIN := $(COVERAGE_DIR)/tests/hushwheel_unit
HARDENED_DIR := $(BUILD_DIR)/hardened
HARDENED_BIN := $(HARDENED_DIR)/hushwheel
HARDENED_UNIT_BIN := $(HARDENED_DIR)/tests/hushwheel_unit
SANITIZER_DIR := $(BUILD_DIR)/sanitizers
SANITIZER_BIN := $(SANITIZER_DIR)/hushwheel
SANITIZER_UNIT_BIN := $(SANITIZER_DIR)/tests/hushwheel_unit
PROFILE_DIR := $(BUILD_DIR)/profile
PROFILE_BIN := $(PROFILE_DIR)/hushwheel
REPORT_DIR := $(BUILD_DIR)/reports
REPORT_SUMMARY := $(REPORT_DIR)/quality-summary.md
CPPCHECK_DIR := $(REPORT_DIR)/cppcheck
CPPCHECK_XML := $(CPPCHECK_DIR)/cppcheck.xml
CPPCHECK_TXT := $(CPPCHECK_DIR)/cppcheck.txt
COMPLEXITY_DIR := $(REPORT_DIR)/complexity
COMPLEXITY_XML := $(COMPLEXITY_DIR)/lizard-checkstyle.xml
COMPLEXITY_CSV := $(COMPLEXITY_DIR)/lizard.csv
COMPLEXITY_TXT := $(COMPLEXITY_DIR)/lizard.txt
COVERAGE_REPORT_DIR := $(REPORT_DIR)/coverage
COVERAGE_XML := $(COVERAGE_REPORT_DIR)/coverage.xml
COVERAGE_TXT := $(COVERAGE_REPORT_DIR)/coverage.txt
COVERAGE_HTML := $(COVERAGE_REPORT_DIR)/index.html
COVERAGE_JSON := $(COVERAGE_REPORT_DIR)/coverage-summary.json
COVERAGE_SUMMARY_MD := $(COVERAGE_REPORT_DIR)/coverage-summary.md
HARDENING_REPORT_DIR := $(REPORT_DIR)/hardening
HARDENING_FILE_TXT := $(HARDENING_REPORT_DIR)/file.txt
HARDENING_SIZE_TXT := $(HARDENING_REPORT_DIR)/size.txt
HARDENING_HEADER_TXT := $(HARDENING_REPORT_DIR)/readelf-header.txt
HARDENING_PROGRAM_TXT := $(HARDENING_REPORT_DIR)/readelf-program-headers.txt
HARDENING_DYNAMIC_TXT := $(HARDENING_REPORT_DIR)/readelf-dynamic.txt
HARDENING_SYMBOLS_TXT := $(HARDENING_REPORT_DIR)/symbols.txt
HARDENING_UNIT_LOG := $(HARDENING_REPORT_DIR)/unit.log
HARDENING_INTEGRATION_LOG := $(HARDENING_REPORT_DIR)/integration.log
HARDENING_BDD_LOG := $(HARDENING_REPORT_DIR)/bdd.log
HARDENING_SUMMARY_MD := $(HARDENING_REPORT_DIR)/hardening-summary.md
SANITIZER_REPORT_DIR := $(REPORT_DIR)/sanitizers
SANITIZER_UNIT_LOG := $(SANITIZER_REPORT_DIR)/unit.log
SANITIZER_INTEGRATION_LOG := $(SANITIZER_REPORT_DIR)/integration.log
SANITIZER_BDD_LOG := $(SANITIZER_REPORT_DIR)/bdd.log
SANITIZER_SUMMARY_MD := $(SANITIZER_REPORT_DIR)/sanitizers-summary.md
PROFILE_REPORT_DIR := $(REPORT_DIR)/profiling
PROFILE_DATA_TSV := $(PROFILE_REPORT_DIR)/runtime-profile.tsv
PROFILE_WORKLOAD_TXT := $(PROFILE_REPORT_DIR)/workload.txt
PROFILE_MD := $(PROFILE_REPORT_DIR)/runtime-profile.md
LIZARD_CCN_LIMIT ?= 15
LIZARD_LENGTH_LIMIT ?= 80
LIZARD_PARAM_LIMIT ?= 6
COVERAGE_LINE_MIN ?= 95
COVERAGE_FUNCTION_MIN ?= 100
STAGE_DIR := $(BUILD_DIR)/dist/$(PACKAGE_NAME)-$(VERSION)
DIST_ARCHIVE := $(DIST_DIR)/$(PACKAGE_NAME)-$(VERSION).tar.gz
DOC_FILES := \
	README.md \
	CHANGELOG.md \
	LICENSE.md \
	docs/concepts.md \
	docs/operations.md \
	docs/districts.md \
	docs/catalog.md \
	docs/constellation-atlas.md \
	docs/architecture.md \
	docs/testing.md \
	docs/packaging.md \
	docs/doxygen-fonts.sty
PACKAGE_FILES := \
	Makefile \
	Doxyfile \
	VERSION \
	fixture-manifest.json \
	include/hushwheel.h \
	$(SRC_HEADERS) \
	$(SRC_FILES) \
	packaging/hushwheel.package.json \
	packaging/hushwheel.1 \
	tests/unit/test_hushwheel_unit.c \
	tests/integration/cli_suite.py \
	tests/bdd/hushwheel.feature \
	tests/bdd/run_bdd.py \
	tools/lint_hushwheel.py \
	tools/regenerate_hushwheel_fixture.py \
	$(DOC_FILES) \
	$(DOC_PDF)

export TMPDIR
.PHONY: all bdd check clean complexity coverage dist docs hardening install integration lint package profiling quality regenerate reports sanitizers static-analysis test unit uninstall

all: hushwheel

hushwheel: $(SRC_FILES) $(SRC_HEADERS) include/hushwheel.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -Iinclude -Isrc $(SRC_FILES) -o $@

$(UNIT_BIN): tests/unit/test_hushwheel_unit.c $(SRC_FILES) $(SRC_HEADERS) include/hushwheel.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) -DHUSHWHEEL_NO_MAIN -Iinclude -Isrc tests/unit/test_hushwheel_unit.c $(SRC_FILES) -o $@

$(BUILD_DIR)/lint/%.o: src/%.c $(SRC_HEADERS) include/hushwheel.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LINT_CFLAGS) -DHUSHWHEEL_NO_MAIN -Iinclude -Isrc -c $< -o $@

lint: $(LINT_OBJS)
	$(PYTHON) tools/lint_hushwheel.py

static-analysis:
	rm -rf $(CPPCHECK_DIR)
	mkdir -p $(CPPCHECK_DIR)
	mkdir -p $(CPPCHECK_DIR) && $(CPPCHECK) --enable=warning,style,performance,portability --std=c99 --language=c --check-level=exhaustive --error-exitcode=1 -Iinclude -Isrc --xml-version=2 src include 2>$(CPPCHECK_XML)
	mkdir -p $(CPPCHECK_DIR) && $(CPPCHECK) --enable=warning,style,performance,portability --std=c99 --language=c --check-level=exhaustive --error-exitcode=1 -Iinclude -Isrc --template=gcc src include >/dev/null 2>$(CPPCHECK_TXT)

complexity:
	rm -rf $(COMPLEXITY_DIR)
	mkdir -p $(COMPLEXITY_DIR) && $(LIZARD) -l c -C $(LIZARD_CCN_LIMIT) -L $(LIZARD_LENGTH_LIMIT) -a $(LIZARD_PARAM_LIMIT) src include tests/unit/test_hushwheel_unit.c >$(COMPLEXITY_TXT)
	mkdir -p $(COMPLEXITY_DIR) && $(LIZARD) -l c -C $(LIZARD_CCN_LIMIT) -L $(LIZARD_LENGTH_LIMIT) -a $(LIZARD_PARAM_LIMIT) --csv src include tests/unit/test_hushwheel_unit.c >$(COMPLEXITY_CSV)
	mkdir -p $(COMPLEXITY_DIR) && $(LIZARD) -l c -C $(LIZARD_CCN_LIMIT) -L $(LIZARD_LENGTH_LIMIT) -a $(LIZARD_PARAM_LIMIT) --checkstyle src include tests/unit/test_hushwheel_unit.c >$(COMPLEXITY_XML)

$(DOC_PDF): $(DOXYFILE) README.md include/hushwheel.h $(SRC_FILES) $(SRC_HEADERS) $(DOC_FILES)
	@if command -v $(DOXYGEN) >/dev/null 2>&1 \
		&& rm -rf $(DOC_BUILD_DIR) \
		&& mkdir -p $(DOC_BUILD_DIR) $(TMPDIR) \
		&& $(DOXYGEN) $(DOXYFILE) \
		&& (cd $(DOC_BUILD_DIR)/latex && lualatex -interaction=nonstopmode -halt-on-error refman >/dev/null) \
		&& (cd $(DOC_BUILD_DIR)/latex && makeindex refman.idx >/dev/null) \
		&& (cd $(DOC_BUILD_DIR)/latex && lualatex -interaction=nonstopmode -halt-on-error refman >/dev/null) \
		&& (cd $(DOC_BUILD_DIR)/latex && lualatex -interaction=nonstopmode -halt-on-error refman >/dev/null) \
		&& [ -f "$(DOC_BUILD_DIR)/latex/refman.pdf" ]; then \
		install -m 0644 $(DOC_BUILD_DIR)/latex/refman.pdf $@; \
	elif [ -f "$@" ]; then \
		echo "using committed $(DOC_PDF) because generated docs are unavailable"; \
	else \
		echo "generated docs unavailable and $(DOC_PDF) is missing" >&2; \
		exit 127; \
	fi

docs: $(DOC_PDF)

unit: $(UNIT_BIN)
	./$(UNIT_BIN)

integration: hushwheel
	HUSHWHEEL_BIN="$(HUSHWHEEL_BIN)" $(PYTHON) tests/integration/cli_suite.py

bdd: hushwheel
	HUSHWHEEL_BIN="$(HUSHWHEEL_BIN)" $(PYTHON) tests/bdd/run_bdd.py

check: lint unit integration bdd

$(COVERAGE_BIN): $(SRC_FILES) $(SRC_HEADERS) include/hushwheel.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(COVERAGE_CFLAGS) -Iinclude -Isrc $(SRC_FILES) -o $@

$(COVERAGE_UNIT_BIN): tests/unit/test_hushwheel_unit.c $(SRC_FILES) $(SRC_HEADERS) include/hushwheel.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(COVERAGE_CFLAGS) -DHUSHWHEEL_NO_MAIN -Iinclude -Isrc tests/unit/test_hushwheel_unit.c $(SRC_FILES) -o $@

coverage: $(COVERAGE_BIN) $(COVERAGE_UNIT_BIN)
	rm -rf $(COVERAGE_REPORT_DIR)
	mkdir -p $(COVERAGE_REPORT_DIR)
	find $(COVERAGE_DIR) -name '*.gcda' -delete
	./$(COVERAGE_UNIT_BIN)
	HUSHWHEEL_BIN="$(abspath $(COVERAGE_BIN))" $(PYTHON) tests/integration/cli_suite.py
	HUSHWHEEL_BIN="$(abspath $(COVERAGE_BIN))" $(PYTHON) tests/bdd/run_bdd.py
	$(GCOVR) -r . --gcov-object-directory $(COVERAGE_DIR) --filter 'src/' --exclude 'src/hushwheel_spoke_.*[.]c$$' --exclude 'src/hushwheel_spokes[.]c$$' --exclude-unreachable-branches --exclude-noncode-lines --xml-pretty --xml $(COVERAGE_XML) --html-details $(COVERAGE_HTML) --html-title "Hushwheel Coverage Report" --txt $(COVERAGE_TXT) --json-summary-pretty --json-summary $(COVERAGE_JSON) --markdown-summary $(COVERAGE_SUMMARY_MD) --fail-under-line $(COVERAGE_LINE_MIN) --fail-under-function $(COVERAGE_FUNCTION_MIN)

$(HARDENED_BIN): $(SRC_FILES) $(SRC_HEADERS) include/hushwheel.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(HARDENED_CFLAGS) -Iinclude -Isrc $(SRC_FILES) $(HARDENED_LDFLAGS) -o $@

$(HARDENED_UNIT_BIN): tests/unit/test_hushwheel_unit.c $(SRC_FILES) $(SRC_HEADERS) include/hushwheel.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(HARDENED_CFLAGS) -DHUSHWHEEL_NO_MAIN -Iinclude -Isrc tests/unit/test_hushwheel_unit.c $(SRC_FILES) $(HARDENED_LDFLAGS) -o $@

hardening: $(HARDENED_BIN) $(HARDENED_UNIT_BIN)
	rm -rf $(HARDENING_REPORT_DIR)
	mkdir -p $(HARDENING_REPORT_DIR)
	./$(HARDENED_UNIT_BIN) >$(HARDENING_UNIT_LOG) 2>&1
	HUSHWHEEL_BIN="$(abspath $(HARDENED_BIN))" $(PYTHON) tests/integration/cli_suite.py >$(HARDENING_INTEGRATION_LOG) 2>&1
	HUSHWHEEL_BIN="$(abspath $(HARDENED_BIN))" $(PYTHON) tests/bdd/run_bdd.py >$(HARDENING_BDD_LOG) 2>&1
	file $(HARDENED_BIN) >$(HARDENING_FILE_TXT)
	size $(HARDENED_BIN) >$(HARDENING_SIZE_TXT)
	readelf -W -h $(HARDENED_BIN) >$(HARDENING_HEADER_TXT)
	readelf -W -l $(HARDENED_BIN) >$(HARDENING_PROGRAM_TXT)
	readelf -W -d $(HARDENED_BIN) >$(HARDENING_DYNAMIC_TXT)
	nm -an $(HARDENED_BIN) >$(HARDENING_SYMBOLS_TXT)
	pie_status=$$(grep -q 'DYN (Position-Independent Executable file)' $(HARDENING_HEADER_TXT) && printf 'pass' || printf 'fail'); \
	relro_status=$$(grep -q 'GNU_RELRO' $(HARDENING_PROGRAM_TXT) && printf 'pass' || printf 'fail'); \
	now_status=$$(grep -Eq 'BIND_NOW|Flags: NOW PIE' $(HARDENING_DYNAMIC_TXT) && printf 'pass' || printf 'fail'); \
	nx_status=$$(awk '/GNU_STACK/ { permissions = $$(NF-1); if (index(permissions, "E") == 0) { print "pass"; exit 0 } exit 1 } END { if (NR == 0) { exit 1 } }' $(HARDENING_PROGRAM_TXT) || printf 'fail'); \
	stack_status=$$(grep -q '__stack_chk_fail' $(HARDENING_SYMBOLS_TXT) && printf 'detected' || printf 'not-detected'); \
	printf '# Hushwheel Binary Hardening Report\n\n' >$(HARDENING_SUMMARY_MD); \
	printf -- '- binary: `%s`\n' '$(abspath $(HARDENED_BIN))' >>$(HARDENING_SUMMARY_MD); \
	printf -- '- configured cflags: `%s`\n' '$(CFLAGS) $(HARDENED_CFLAGS)' >>$(HARDENING_SUMMARY_MD); \
	printf -- '- configured ldflags: `%s`\n' '$(HARDENED_LDFLAGS)' >>$(HARDENING_SUMMARY_MD); \
	printf '\n## ELF Checks\n\n| Check | Status |\n| --- | --- |\n' >>$(HARDENING_SUMMARY_MD); \
	printf '| PIE | %s |\n' "$$pie_status" >>$(HARDENING_SUMMARY_MD); \
	printf '| RELRO segment | %s |\n' "$$relro_status" >>$(HARDENING_SUMMARY_MD); \
	printf '| BIND_NOW | %s |\n' "$$now_status" >>$(HARDENING_SUMMARY_MD); \
	printf '| Non-executable stack | %s |\n' "$$nx_status" >>$(HARDENING_SUMMARY_MD); \
	printf '| Stack protector symbol | %s |\n' "$$stack_status" >>$(HARDENING_SUMMARY_MD); \
	printf '\n## Artifacts\n\n' >>$(HARDENING_SUMMARY_MD); \
	printf -- '- `file`: `%s`\n' '$(HARDENING_FILE_TXT)' >>$(HARDENING_SUMMARY_MD); \
	printf -- '- `size`: `%s`\n' '$(HARDENING_SIZE_TXT)' >>$(HARDENING_SUMMARY_MD); \
	printf -- '- `readelf -h`: `%s`\n' '$(HARDENING_HEADER_TXT)' >>$(HARDENING_SUMMARY_MD); \
	printf -- '- `readelf -l`: `%s`\n' '$(HARDENING_PROGRAM_TXT)' >>$(HARDENING_SUMMARY_MD); \
	printf -- '- `readelf -d`: `%s`\n' '$(HARDENING_DYNAMIC_TXT)' >>$(HARDENING_SUMMARY_MD); \
	printf -- '- `nm -an`: `%s`\n' '$(HARDENING_SYMBOLS_TXT)' >>$(HARDENING_SUMMARY_MD); \
	printf -- '- hardening unit log: `%s`\n' '$(HARDENING_UNIT_LOG)' >>$(HARDENING_SUMMARY_MD); \
	printf -- '- hardening integration log: `%s`\n' '$(HARDENING_INTEGRATION_LOG)' >>$(HARDENING_SUMMARY_MD); \
	printf -- '- hardening BDD log: `%s`\n' '$(HARDENING_BDD_LOG)' >>$(HARDENING_SUMMARY_MD); \
	test "$$pie_status" = pass && test "$$relro_status" = pass && test "$$now_status" = pass && test "$$nx_status" = pass

$(SANITIZER_BIN): $(SRC_FILES) $(SRC_HEADERS) include/hushwheel.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(SANITIZER_CFLAGS) -Iinclude -Isrc $(SRC_FILES) $(SANITIZER_LDFLAGS) -o $@

$(SANITIZER_UNIT_BIN): tests/unit/test_hushwheel_unit.c $(SRC_FILES) $(SRC_HEADERS) include/hushwheel.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(SANITIZER_CFLAGS) -DHUSHWHEEL_NO_MAIN -Iinclude -Isrc tests/unit/test_hushwheel_unit.c $(SRC_FILES) $(SANITIZER_LDFLAGS) -o $@

sanitizers: $(SANITIZER_BIN) $(SANITIZER_UNIT_BIN)
	rm -rf $(SANITIZER_REPORT_DIR)
	mkdir -p $(SANITIZER_REPORT_DIR)
	ASAN_OPTIONS='detect_leaks=1:halt_on_error=1:strict_string_checks=1:check_initialization_order=1' UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1' ./$(SANITIZER_UNIT_BIN) >$(SANITIZER_UNIT_LOG) 2>&1
	ASAN_OPTIONS='detect_leaks=1:halt_on_error=1:strict_string_checks=1:check_initialization_order=1' UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1' HUSHWHEEL_BIN="$(abspath $(SANITIZER_BIN))" $(PYTHON) tests/integration/cli_suite.py >$(SANITIZER_INTEGRATION_LOG) 2>&1
	ASAN_OPTIONS='detect_leaks=1:halt_on_error=1:strict_string_checks=1:check_initialization_order=1' UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1' HUSHWHEEL_BIN="$(abspath $(SANITIZER_BIN))" $(PYTHON) tests/bdd/run_bdd.py >$(SANITIZER_BDD_LOG) 2>&1
	printf '# Hushwheel Sanitizer Report\n\n' >$(SANITIZER_SUMMARY_MD)
	printf -- '- binary: `%s`\n' '$(abspath $(SANITIZER_BIN))' >>$(SANITIZER_SUMMARY_MD)
	printf -- '- unit binary: `%s`\n' '$(abspath $(SANITIZER_UNIT_BIN))' >>$(SANITIZER_SUMMARY_MD)
	printf -- '- configured cflags: `%s`\n' '$(CFLAGS) $(SANITIZER_CFLAGS)' >>$(SANITIZER_SUMMARY_MD)
	printf -- '- configured ldflags: `%s`\n' '$(SANITIZER_LDFLAGS)' >>$(SANITIZER_SUMMARY_MD)
	printf -- '- ASAN_OPTIONS: `%s`\n' 'detect_leaks=1:halt_on_error=1:strict_string_checks=1:check_initialization_order=1' >>$(SANITIZER_SUMMARY_MD)
	printf -- '- UBSAN_OPTIONS: `%s`\n' 'halt_on_error=1:print_stacktrace=1' >>$(SANITIZER_SUMMARY_MD)
	printf '\n## Logs\n\n' >>$(SANITIZER_SUMMARY_MD)
	printf -- '- unit: `%s`\n' '$(SANITIZER_UNIT_LOG)' >>$(SANITIZER_SUMMARY_MD)
	printf -- '- integration: `%s`\n' '$(SANITIZER_INTEGRATION_LOG)' >>$(SANITIZER_SUMMARY_MD)
	printf -- '- BDD: `%s`\n' '$(SANITIZER_BDD_LOG)' >>$(SANITIZER_SUMMARY_MD)

$(PROFILE_BIN): $(SRC_FILES) $(SRC_HEADERS) include/hushwheel.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(PROFILE_CFLAGS) -Iinclude -Isrc $(SRC_FILES) -o $@

profiling: $(PROFILE_BIN)
	rm -rf $(PROFILE_REPORT_DIR)
	mkdir -p $(PROFILE_REPORT_DIR)
	printf '%s\n' \
		'about|about' \
		'stats|stats' \
		'lookup-canonical|lookup ember-index' \
		'lookup-generated|lookup argent-ember-index-0279' \
		'prefix-canonical|prefix amber' \
		'prefix-generated|prefix argent-ember-index' \
		'category-storm|category storm-index' >$(PROFILE_WORKLOAD_TXT)
	: >$(PROFILE_DATA_TSV)
	while IFS='|' read -r scenario_name scenario_args; do \
		stdout_path="$(PROFILE_REPORT_DIR)/$$scenario_name.stdout.txt"; \
		stderr_path="$(PROFILE_REPORT_DIR)/$$scenario_name.stderr.txt"; \
		iteration=1; \
		while [ "$$iteration" -le "$(PROFILE_ITERATIONS)" ]; do \
			stdout_tmp="$(PROFILE_REPORT_DIR)/.$${scenario_name}.$${iteration}.stdout.tmp"; \
			stderr_tmp="$(PROFILE_REPORT_DIR)/.$${scenario_name}.$${iteration}.stderr.tmp"; \
			start_ns=$$(date +%s%N); \
			"$(abspath $(PROFILE_BIN))" $$scenario_args >"$$stdout_tmp" 2>"$$stderr_tmp"; \
			end_ns=$$(date +%s%N); \
			if [ "$$iteration" -eq 1 ]; then \
				mv "$$stdout_tmp" "$$stdout_path"; \
				mv "$$stderr_tmp" "$$stderr_path"; \
			else \
				rm -f "$$stdout_tmp" "$$stderr_tmp"; \
			fi; \
			duration_ns=$$((end_ns - start_ns)); \
			printf '%s\t%s\t%s\n' "$$scenario_name" "$$iteration" "$$duration_ns" >>$(PROFILE_DATA_TSV); \
			iteration=$$((iteration + 1)); \
		done; \
	done <$(PROFILE_WORKLOAD_TXT)
	printf '# Hushwheel Runtime Profile\n\n' >$(PROFILE_MD)
	printf -- '- binary: `%s`\n' '$(abspath $(PROFILE_BIN))' >>$(PROFILE_MD)
	printf -- '- iterations per scenario: `%s`\n' '$(PROFILE_ITERATIONS)' >>$(PROFILE_MD)
	printf -- '- workload manifest: `%s`\n' '$(PROFILE_WORKLOAD_TXT)' >>$(PROFILE_MD)
	printf -- '- raw timing data: `%s`\n' '$(PROFILE_DATA_TSV)' >>$(PROFILE_MD)
	printf '\n## Scenario Timings\n\n| Scenario | Iterations | Mean ms | Min ms | Max ms |\n| --- | ---: | ---: | ---: | ---: |\n' >>$(PROFILE_MD)
	cut -f1 $(PROFILE_DATA_TSV) | sort -u | while read -r scenario_name; do \
		awk -F '\t' -v scenario="$$scenario_name" '$$1 == scenario { count += 1; total += $$3; if (count == 1 || $$3 < min) min = $$3; if ($$3 > max) max = $$3 } END { printf "| %s | %d | %.3f | %.3f | %.3f |\n", scenario, count, (total / count) / 1000000.0, min / 1000000.0, max / 1000000.0 }' $(PROFILE_DATA_TSV) >>$(PROFILE_MD); \
	done
	printf '\n## Sample Logs\n\n' >>$(PROFILE_MD)
	find $(PROFILE_REPORT_DIR) -maxdepth 1 \( -name '*.stdout.txt' -o -name '*.stderr.txt' \) | sort | while read -r log_path; do \
		printf -- '- `%s`\n' "$$log_path" >>$(PROFILE_MD); \
	done

reports: static-analysis complexity coverage hardening sanitizers profiling
	mkdir -p $(REPORT_DIR)
	printf '# Hushwheel Quality Reports\n\n' >$(REPORT_SUMMARY)
	printf 'Generated by `make quality`.\n\n' >>$(REPORT_SUMMARY)
	printf '## Artifacts\n\n' >>$(REPORT_SUMMARY)
	printf -- '- `cppcheck` XML: `%s`\n' '$(CPPCHECK_XML)' >>$(REPORT_SUMMARY)
	printf -- '- `cppcheck` text: `%s`\n' '$(CPPCHECK_TXT)' >>$(REPORT_SUMMARY)
	printf -- '- `lizard` text: `%s`\n' '$(COMPLEXITY_TXT)' >>$(REPORT_SUMMARY)
	printf -- '- `lizard` CSV: `%s`\n' '$(COMPLEXITY_CSV)' >>$(REPORT_SUMMARY)
	printf -- '- `lizard` checkstyle XML: `%s`\n' '$(COMPLEXITY_XML)' >>$(REPORT_SUMMARY)
	printf -- '- `gcovr` text: `%s`\n' '$(COVERAGE_TXT)' >>$(REPORT_SUMMARY)
	printf -- '- `gcovr` Cobertura XML: `%s`\n' '$(COVERAGE_XML)' >>$(REPORT_SUMMARY)
	printf -- '- `gcovr` HTML: `%s`\n' '$(COVERAGE_HTML)' >>$(REPORT_SUMMARY)
	printf -- '- `gcovr` JSON summary: `%s`\n' '$(COVERAGE_JSON)' >>$(REPORT_SUMMARY)
	printf -- '- hardening summary: `%s`\n' '$(HARDENING_SUMMARY_MD)' >>$(REPORT_SUMMARY)
	printf -- '- sanitizer summary: `%s`\n' '$(SANITIZER_SUMMARY_MD)' >>$(REPORT_SUMMARY)
	printf -- '- runtime profile: `%s`\n' '$(PROFILE_MD)' >>$(REPORT_SUMMARY)
	printf -- '- runtime profile timings: `%s`\n' '$(PROFILE_DATA_TSV)' >>$(REPORT_SUMMARY)
	printf '\n## Binary Hardening Summary\n\n' >>$(REPORT_SUMMARY)
	cat $(HARDENING_SUMMARY_MD) >>$(REPORT_SUMMARY)
	printf '\n\n## Sanitizer Summary\n\n' >>$(REPORT_SUMMARY)
	cat $(SANITIZER_SUMMARY_MD) >>$(REPORT_SUMMARY)
	printf '\n\n## Runtime Profile\n\n' >>$(REPORT_SUMMARY)
	cat $(PROFILE_MD) >>$(REPORT_SUMMARY)
	printf '\n\n## Coverage Summary\n\n' >>$(REPORT_SUMMARY)
	cat $(COVERAGE_SUMMARY_MD) >>$(REPORT_SUMMARY)

quality: check reports

test: check

regenerate:
	$(PYTHON) tools/regenerate_hushwheel_fixture.py

$(DIST_ARCHIVE): $(PACKAGE_FILES)
	mkdir -p $(DIST_DIR) $(dir $(STAGE_DIR))
	rm -rf $(STAGE_DIR)
	mkdir -p $(STAGE_DIR)
	tar -cf - $(PACKAGE_FILES) | tar -xf - -C $(STAGE_DIR)
	tar -czf $@ -C $(BUILD_DIR)/dist $(PACKAGE_NAME)-$(VERSION)

dist: $(DIST_ARCHIVE)

package: dist

install: hushwheel $(DOC_PDF)
	install -d $(DESTDIR)$(BINDIR)
	install -d $(DESTDIR)$(DOCDIR)
	install -d $(DESTDIR)$(DOCDIR)/docs
	install -d $(DESTDIR)$(DOCDIR)/packaging
	install -d $(DESTDIR)$(MANDIR)/man1
	install -m 0755 hushwheel $(DESTDIR)$(BINDIR)/hushwheel
	install -m 0644 README.md CHANGELOG.md LICENSE.md VERSION fixture-manifest.json $(DESTDIR)$(DOCDIR)/
	install -m 0644 docs/concepts.md docs/operations.md docs/districts.md docs/catalog.md $(DESTDIR)$(DOCDIR)/docs/
	install -m 0644 docs/constellation-atlas.md docs/architecture.md docs/testing.md docs/packaging.md docs/hushwheel-reference.pdf $(DESTDIR)$(DOCDIR)/docs/
	install -m 0644 packaging/hushwheel.package.json $(DESTDIR)$(DOCDIR)/packaging/
	install -m 0644 packaging/hushwheel.1 $(DESTDIR)$(MANDIR)/man1/hushwheel.1

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/hushwheel
	rm -f $(DESTDIR)$(MANDIR)/man1/hushwheel.1
	rm -rf $(DESTDIR)$(DOCDIR)

clean:
	rm -rf hushwheel $(BUILD_DIR) $(DIST_DIR)
