CC ?= cc
PYTHON ?= python3
CPPFLAGS ?=
CFLAGS ?= -std=c99 -O2 -Wall -Wextra -pedantic
LINT_CFLAGS ?= -Werror -Wstrict-prototypes -Wold-style-definition
PREFIX ?= /usr/local
DESTDIR ?=
PACKAGE_NAME ?= hushwheel
VERSION := $(strip $(shell cat VERSION))
BINDIR ?= $(PREFIX)/bin
DOCDIR ?= $(PREFIX)/share/doc/$(PACKAGE_NAME)
MANDIR ?= $(PREFIX)/share/man
BUILD_DIR := build
DIST_DIR := dist
UNIT_BIN := $(BUILD_DIR)/tests/hushwheel_unit
LINT_OBJ := $(BUILD_DIR)/lint/hushwheel.o
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
	docs/packaging.md
PACKAGE_FILES := \
	Makefile \
	VERSION \
	fixture-manifest.json \
	include/hushwheel.h \
	src/hushwheel.c \
	packaging/hushwheel.package.json \
	packaging/hushwheel.1 \
	tests/unit/test_hushwheel_unit.c \
	tests/integration/cli_suite.py \
	tests/bdd/hushwheel.feature \
	tests/bdd/run_bdd.py \
	tools/lint_hushwheel.py \
	$(DOC_FILES)

.PHONY: all bdd check clean dist install integration lint package test unit uninstall

all: hushwheel

hushwheel: src/hushwheel.c include/hushwheel.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -Iinclude src/hushwheel.c -o $@

$(UNIT_BIN): tests/unit/test_hushwheel_unit.c src/hushwheel.c include/hushwheel.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) -Iinclude tests/unit/test_hushwheel_unit.c -o $@

$(LINT_OBJ): src/hushwheel.c include/hushwheel.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LINT_CFLAGS) -DHUSHWHEEL_NO_MAIN -Iinclude -c src/hushwheel.c -o $@

lint: $(LINT_OBJ)
	$(PYTHON) tools/lint_hushwheel.py

unit: $(UNIT_BIN)
	./$(UNIT_BIN)

integration: hushwheel
	$(PYTHON) tests/integration/cli_suite.py

bdd: hushwheel
	$(PYTHON) tests/bdd/run_bdd.py

check: lint unit integration bdd

test: check

$(DIST_ARCHIVE): $(PACKAGE_FILES)
	mkdir -p $(DIST_DIR) $(dir $(STAGE_DIR))
	rm -rf $(STAGE_DIR)
	mkdir -p $(STAGE_DIR)
	tar -cf - $(PACKAGE_FILES) | tar -xf - -C $(STAGE_DIR)
	tar -czf $@ -C $(BUILD_DIR)/dist $(PACKAGE_NAME)-$(VERSION)

dist: $(DIST_ARCHIVE)

package: dist

install: hushwheel
	install -d $(DESTDIR)$(BINDIR)
	install -d $(DESTDIR)$(DOCDIR)
	install -d $(DESTDIR)$(DOCDIR)/docs
	install -d $(DESTDIR)$(DOCDIR)/packaging
	install -d $(DESTDIR)$(MANDIR)/man1
	install -m 0755 hushwheel $(DESTDIR)$(BINDIR)/hushwheel
	install -m 0644 README.md CHANGELOG.md LICENSE.md VERSION fixture-manifest.json $(DESTDIR)$(DOCDIR)/
	install -m 0644 docs/concepts.md docs/operations.md docs/districts.md docs/catalog.md $(DESTDIR)$(DOCDIR)/docs/
	install -m 0644 docs/architecture.md docs/testing.md docs/packaging.md $(DESTDIR)$(DOCDIR)/docs/
	install -m 0644 packaging/hushwheel.package.json $(DESTDIR)$(DOCDIR)/packaging/
	install -m 0644 packaging/hushwheel.1 $(DESTDIR)$(MANDIR)/man1/hushwheel.1

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/hushwheel
	rm -f $(DESTDIR)$(MANDIR)/man1/hushwheel.1
	rm -rf $(DESTDIR)$(DOCDIR)

clean:
	rm -rf hushwheel $(BUILD_DIR) $(DIST_DIR)
