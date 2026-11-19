# Delegates to the backend Makefile so `make verify` works from the repo root.
%:
	$(MAKE) -C services/backend $@
