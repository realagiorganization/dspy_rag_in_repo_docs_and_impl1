CC ?= cc
PYTHON ?= python3
CPPFLAGS ?=
CFLAGS ?= -std=c99 -O2 -Wall -Wextra -pedantic
LINT_CFLAGS ?= -Werror -Wstrict-prototypes -Wold-style-definition
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
SRC_FILES := $(sort $(wildcard src/*.c))
SRC_HEADERS := $(sort $(wildcard src/*.h))
UNIT_BIN := $(BUILD_DIR)/tests/hushwheel_unit
LINT_OBJS := $(patsubst src/%.c,$(BUILD_DIR)/lint/%.o,$(SRC_FILES))
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

.PHONY: all bdd check clean dist docs install integration lint package regenerate test unit uninstall

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

$(DOC_PDF): $(DOXYFILE) README.md include/hushwheel.h $(SRC_FILES) $(SRC_HEADERS) $(DOC_FILES)
	@if command -v $(DOXYGEN) >/dev/null 2>&1; then \
		rm -rf $(DOC_BUILD_DIR); \
		mkdir -p $(DOC_BUILD_DIR); \
		$(DOXYGEN) $(DOXYFILE); \
		(cd $(DOC_BUILD_DIR)/latex && lualatex -interaction=nonstopmode -halt-on-error refman >/dev/null); \
		(cd $(DOC_BUILD_DIR)/latex && makeindex refman.idx >/dev/null); \
		(cd $(DOC_BUILD_DIR)/latex && lualatex -interaction=nonstopmode -halt-on-error refman >/dev/null); \
		(cd $(DOC_BUILD_DIR)/latex && lualatex -interaction=nonstopmode -halt-on-error refman >/dev/null); \
		install -m 0644 $(DOC_BUILD_DIR)/latex/refman.pdf $@; \
	elif [ -f "$@" ]; then \
		echo "using committed $(DOC_PDF) because doxygen is unavailable"; \
	else \
		echo "doxygen not found and $(DOC_PDF) is missing" >&2; \
		exit 127; \
	fi

docs: $(DOC_PDF)

unit: $(UNIT_BIN)
	./$(UNIT_BIN)

integration: hushwheel
	$(PYTHON) tests/integration/cli_suite.py

bdd: hushwheel
	$(PYTHON) tests/bdd/run_bdd.py

check: lint unit integration bdd

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
