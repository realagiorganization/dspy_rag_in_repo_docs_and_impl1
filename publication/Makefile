UV ?= uv
REPO_ROOT := ..
ARTICLE := repository-rag-lab-article
BUILD_DIR := .build
PDF := $(ARTICLE).pdf
BANNER := article-banner.png
RASTER := $(BUILD_DIR)/$(ARTICLE)-page1.png
TODO_TABLE := todo-backlog-table.tex
EXPLORATORIUM_DIR := exploratorium_translation

.PHONY: build pdf banner exploratorium sync-backlog clean

build: $(PDF) $(BANNER) exploratorium

pdf: $(PDF)

banner: $(BANNER)

exploratorium:
	$(MAKE) -C $(EXPLORATORIUM_DIR) build

sync-backlog:
	cd $(REPO_ROOT) && $(UV) run repo-rag sync-todo-backlog --root .

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(TODO_TABLE): $(REPO_ROOT)/todo-backlog.yaml $(REPO_ROOT)/src/repo_rag_lab/todo_backlog.py $(REPO_ROOT)/src/repo_rag_lab/cli.py $(REPO_ROOT)/src/repo_rag_lab/utilities.py
	cd $(REPO_ROOT) && $(UV) run repo-rag sync-todo-backlog --root .

$(PDF): $(ARTICLE).tex references.bib $(TODO_TABLE) | $(BUILD_DIR)
	pdflatex -interaction=nonstopmode -halt-on-error -output-directory=$(BUILD_DIR) $(ARTICLE).tex
	cp references.bib $(BUILD_DIR)/references.bib
	cd $(BUILD_DIR) && bibtex $(ARTICLE)
	pdflatex -interaction=nonstopmode -halt-on-error -output-directory=$(BUILD_DIR) $(ARTICLE).tex
	pdflatex -interaction=nonstopmode -halt-on-error -output-directory=$(BUILD_DIR) $(ARTICLE).tex
	cp $(BUILD_DIR)/$(PDF) $(PDF)

$(RASTER): $(PDF) | $(BUILD_DIR)
	gs -dSAFER -dBATCH -dNOPAUSE -dFirstPage=1 -dLastPage=1 -sDEVICE=pngalpha -r220 -sOutputFile=$(RASTER) $(PDF)

$(BANNER): $(RASTER)
	magick $(RASTER) -background white -alpha remove -alpha off -crop 2200x680+0+0 +repage -resize 1400x433 $(BANNER)

clean:
	$(MAKE) -C $(EXPLORATORIUM_DIR) clean
	rm -rf $(BUILD_DIR) $(PDF) $(BANNER)
