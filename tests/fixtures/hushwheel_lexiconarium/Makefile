CC ?= cc
CFLAGS ?= -std=c99 -O2 -Wall -Wextra -pedantic

all: hushwheel

hushwheel: src/hushwheel.c include/hushwheel.h
	$(CC) $(CFLAGS) -Iinclude src/hushwheel.c -o hushwheel

clean:
	rm -f hushwheel
