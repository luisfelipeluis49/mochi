# Mochi Pi bridge. Build: make   (run scripts/fetch-sdk.sh first)
SDK      := third_party/agora_rtsa_sdk/agora_sdk
SDK_LIB  := $(SDK)/lib/aarch64
CFLAGS   ?= -O2 -g -Wall -Wextra -std=gnu11
CPPFLAGS += -I$(SDK)/include
# rpath: the binary finds the SDK's .so relative to itself, no LD_LIBRARY_PATH needed
LDFLAGS  += -L$(SDK_LIB) -Wl,-rpath,'$$ORIGIN/../$(SDK_LIB)'
LDLIBS   += -lagora-rtc-sdk -lasound -lpthread

build/mochi-bridge: src/bridge.c | $(SDK)/include/agora_rtc_api.h
	@mkdir -p build
	$(CC) $(CPPFLAGS) $(CFLAGS) $< -o $@ $(LDFLAGS) $(LDLIBS)

$(SDK)/include/agora_rtc_api.h:
	./scripts/fetch-sdk.sh

clean:
	rm -rf build

.PHONY: clean
