ARTICLE := repository-rag-lab-article
BUILD_DIR := .build
PDF := $(ARTICLE).pdf
BANNER := article-banner.png
RASTER := $(BUILD_DIR)/$(ARTICLE)-page1.png

.PHONY: build pdf banner clean

build: $(PDF) $(BANNER)

pdf: $(PDF)

banner: $(BANNER)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(PDF): $(ARTICLE).tex references.bib | $(BUILD_DIR)
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
	rm -rf $(BUILD_DIR) $(PDF) $(BANNER)
