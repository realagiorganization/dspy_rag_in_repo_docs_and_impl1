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

.PHONY: all bdd check clean complexity coverage dist docs install integration lint package quality regenerate reports static-analysis test unit uninstall

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
	$(CPPCHECK) --enable=warning,style,performance,portability --std=c99 --language=c --check-level=exhaustive --error-exitcode=1 -Iinclude -Isrc --xml-version=2 src include 2>$(CPPCHECK_XML)
	$(CPPCHECK) --enable=warning,style,performance,portability --std=c99 --language=c --check-level=exhaustive --error-exitcode=1 -Iinclude -Isrc --template=gcc src include >/dev/null 2>$(CPPCHECK_TXT)

complexity:
	rm -rf $(COMPLEXITY_DIR)
	mkdir -p $(COMPLEXITY_DIR)
	$(LIZARD) -l c -C $(LIZARD_CCN_LIMIT) -L $(LIZARD_LENGTH_LIMIT) -a $(LIZARD_PARAM_LIMIT) src include tests/unit/test_hushwheel_unit.c >$(COMPLEXITY_TXT)
	$(LIZARD) -l c -C $(LIZARD_CCN_LIMIT) -L $(LIZARD_LENGTH_LIMIT) -a $(LIZARD_PARAM_LIMIT) --csv src include tests/unit/test_hushwheel_unit.c >$(COMPLEXITY_CSV)
	$(LIZARD) -l c -C $(LIZARD_CCN_LIMIT) -L $(LIZARD_LENGTH_LIMIT) -a $(LIZARD_PARAM_LIMIT) --checkstyle src include tests/unit/test_hushwheel_unit.c >$(COMPLEXITY_XML)

$(DOC_PDF): $(DOXYFILE) README.md include/hushwheel.h $(SRC_FILES) $(SRC_HEADERS) $(DOC_FILES)
	rm -rf $(DOC_BUILD_DIR)
	mkdir -p $(DOC_BUILD_DIR)
	$(DOXYGEN) $(DOXYFILE)
	cd $(DOC_BUILD_DIR)/latex && lualatex -interaction=nonstopmode -halt-on-error refman >/dev/null
	cd $(DOC_BUILD_DIR)/latex && makeindex refman.idx >/dev/null
	cd $(DOC_BUILD_DIR)/latex && lualatex -interaction=nonstopmode -halt-on-error refman >/dev/null
	cd $(DOC_BUILD_DIR)/latex && lualatex -interaction=nonstopmode -halt-on-error refman >/dev/null
	install -m 0644 $(DOC_BUILD_DIR)/latex/refman.pdf $@

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

reports: static-analysis complexity coverage
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
	printf '\n## Coverage Summary\n\n' >>$(REPORT_SUMMARY)
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
	install -m 0644 docs/architecture.md docs/testing.md docs/packaging.md docs/hushwheel-reference.pdf $(DESTDIR)$(DOCDIR)/docs/
	install -m 0644 packaging/hushwheel.package.json $(DESTDIR)$(DOCDIR)/packaging/
	install -m 0644 packaging/hushwheel.1 $(DESTDIR)$(MANDIR)/man1/hushwheel.1

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/hushwheel
	rm -f $(DESTDIR)$(MANDIR)/man1/hushwheel.1
	rm -rf $(DESTDIR)$(DOCDIR)

clean:
	rm -rf hushwheel $(BUILD_DIR) $(DIST_DIR)
