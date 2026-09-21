# Golem top-level build. Every target here is what CI runs; see CLAUDE.md.
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

GENERATED     := src/golem.v
EMET_GENERATED := formal/emet/generated
SBY_JOBS      := $(wildcard formal/*.sby) $(wildcard $(EMET_GENERATED)/*.sby)

.PHONY: all ci rtl unit sim formal check-generated emet check-emet-generated clean

all: ci

# emet (and its check-generated gate) must come before sim/formal: both harnesses
# consume formal/emet/generated/*.
ci: rtl unit check-generated emet check-emet-generated sim formal

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

# The emet compiler (formal/emet/): every ```emet block in spec/'s block files
# (spec/README.md's Files table) -> formal/emet/generated/*.
emet:
	python3 formal/emet/compile.py

# Fails when formal/emet/generated/* differs from what the compiler emits from
# spec/ (a spec edit that wasn't recompiled), the same role check-generated
# plays for src/golem.v.
check-emet-generated: emet
	@if ! git diff --quiet -- $(EMET_GENERATED); then \
	  echo "error: $(EMET_GENERATED) is stale; run 'make emet' and commit." >&2; \
	  git --no-pager diff --stat -- $(EMET_GENERATED) >&2; exit 1; \
	fi

# cocotb tests on the generated Verilog (RTL simulation).
sim:
	cd test && $(MAKE) clean && $(MAKE)
	@! grep -q failure test/results.xml || { echo "error: cocotb failures, see test/results.xml" >&2; exit 1; }

# Every SymbiYosys job; each .sby lists its own tasks (prove, cover, ...).
formal:
	@for job in $(SBY_JOBS); do \
	  echo "== $$job"; \
	  (cd $$(dirname $$job) && sby -f $$(basename $$job)) || exit 1; \
	done

clean:
	cd rtl && dune clean
	cd test && $(MAKE) clean || true
	find formal -mindepth 1 -maxdepth 1 -type d ! -name emet -exec rm -rf {} +
	find $(EMET_GENERATED) -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} +
