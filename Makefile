# Golem top-level build. Every target here is what CI runs; see CLAUDE.md.
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

GENERATED := src/golem.v
SBY_JOBS  := $(wildcard formal/*.sby)

.PHONY: all ci rtl unit sim formal check-generated clean

all: ci

ci: rtl unit check-generated sim formal

# Build the Hardcaml design and regenerate the Verilog Tiny Tapeout consumes.
rtl:
	cd rtl && dune build @install bin/generate.exe
	cd rtl && dune exec --no-build bin/generate.exe -- ../$(GENERATED)

# Designer's Hardcaml expect tests.
unit:
	cd rtl && dune test

# Fails when src/*.v differs from what the OCaml generates (hand edits or a stale commit).
check-generated: rtl
	@if ! git diff --quiet -- $(GENERATED); then \
	  echo "error: $(GENERATED) is stale or hand-edited; run 'make rtl' and commit." >&2; \
	  git --no-pager diff --stat -- $(GENERATED) >&2; exit 1; \
	fi

# cocotb tests on the generated Verilog (RTL simulation).
sim:
	cd test && $(MAKE) clean && $(MAKE)
	@! grep -q failure test/results.xml || { echo "error: cocotb failures, see test/results.xml" >&2; exit 1; }

# Every SymbiYosys job; each .sby lists its own tasks (prove, cover, ...).
formal:
	@for job in $(SBY_JOBS); do \
	  echo "== $$job"; \
	  (cd formal && sby -f $$(basename $$job)) || exit 1; \
	done

clean:
	cd rtl && dune clean
	cd test && $(MAKE) clean || true
	find formal -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} +
