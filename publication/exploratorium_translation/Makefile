UV ?= uv
REPO_ROOT := ../..
ARTICLE := exploratorium_translation
BUILD_DIR := .build
PDF := $(ARTICLE).pdf
LATEX := lualatex
GENERATED_TEX := generated/exploratorium-content.tex
GENERATED_MANIFEST := generated/exploratorium-manifest.json

.PHONY: build sync-data clean

build: $(PDF)

sync-data:
	cd $(REPO_ROOT) && $(UV) run repo-rag sync-exploratorium-translation --root .

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(GENERATED_TEX) $(GENERATED_MANIFEST):
	cd $(REPO_ROOT) && $(UV) run repo-rag sync-exploratorium-translation --root .

$(PDF): $(ARTICLE).tex $(GENERATED_TEX) $(GENERATED_MANIFEST) | $(BUILD_DIR)
	$(LATEX) -interaction=nonstopmode -halt-on-error -output-directory=$(BUILD_DIR) $(ARTICLE).tex
	$(LATEX) -interaction=nonstopmode -halt-on-error -output-directory=$(BUILD_DIR) $(ARTICLE).tex
	cp $(BUILD_DIR)/$(PDF) $(PDF)

clean:
	rm -rf $(BUILD_DIR) $(PDF)
