.PHONY: all clean
CFLAGS ?= -O2 -Wall -Wextra -Werror -std=c11

all: openssl_kex_probe

openssl_kex_probe: openssl_kex_probe.c
	$(CC) $(CFLAGS) $< -o $@ $(shell pkg-config --cflags --libs openssl)

clean:
	rm -f openssl_kex_probe
