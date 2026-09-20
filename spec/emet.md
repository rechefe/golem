# emet — the property language

Status: **v0.** Frozen at the 2026-10-10 milestone. Every check in this directory that can be
written as a property of a clocked interface is written in emet.

emet is small on purpose: six pattern types and one directive, one compile target, and no way
to say anything that a plain-Verilog monitor cannot check. A property written here means the
same thing to the designer, to the verifier, to SymbiYosys and to cocotb, because all four
read the same compiled monitor.

This file is the language reference. It is documentation, not a block spec: the compiler never
reads it, so the emet blocks below are illustrations and constrain nothing.

## What emet is, and what it is not

- **Six patterns, no more**: invariant, `at` (implication at a fixed cycle offset), `within`
  (bounded response), `hold` (hold-for-n), `stable ... until`, and `onehot`/`mutex`. Plus the
  `cover` directive, which is a directive and not a pattern.
- **One compile target**: a plain-Verilog monitor module, used by *both* SymbiYosys and the
  cocotb simulation. One generator, two harnesses, so a property cannot drift between formal
  and sim.
- **No SVA.** Yosys' SVA support is partial and SymbiYosys is happiest with plain `always`
  blocks and immediate asserts. A tooling constraint, not a preference.
- **No OCaml back end.** PLAN.md's executable OCaml reference model stays, written by hand
  against the spec. A property language that also generated the golden model would be
  checking itself.
- **No `assume`.** An assumption constrains a formal engine and is invisible in simulation, so
  the same monitor would mean two different things in the two harnesses. emet has no way to
  write one: a property that needs an input constrained puts that constraint in its trigger,
  and a requirement whose check is a constraint on the harness rather than a property of the
  trace keeps a prose **Acceptance** line instead (see `UTX-FRM-002`).
- The compiler lives in `formal/emet/` — the verifier's lane. This file specifies the
  language; the verifier builds the compiler.

## Where emet lives in the MAS

### The fenced-block convention

An emet block is a fenced code block whose info string is exactly `emet`:

    ```emet
    property UTX-IDL-001 {
      invariant ready -> tx;
    }
    ```

Extraction rules, so that reading the Markdown is unambiguous:

- The block opens with exactly three backticks followed by `emet` and nothing else, at column
  0, and closes with exactly three backticks at column 0.
- The compiler reads the **block specs**: the files listed in the Files table of
  `spec/README.md`, i.e. every `spec/*.md` other than `README.md` and this file. Everything
  else in `spec/` — `workloads/`, prose, tables — is invisible to it.
- A block's **section** is the nearest `###` heading above it. A `property` in a block under a
  requirement's heading belongs to that requirement.
- The `unit` block sits in the block spec's `## Interface` section, directly under the
  interface table.

### Naming, and traceability

A property is named after the requirement it checks: the requirement's ID, optionally followed
by `.` and a lower-case tag when one requirement needs more than one property.

```emet
property UTX-RST-001.tx    { at 1 after clear: tx; }
property UTX-RST-001.ready { at 1 after clear: ready; }
```

The compiler **fails** if a property's ID does not match the ID of the section it sits in.
That is what makes the traceability matrix (PLAN.md) a fact about the spec rather than a
promise: requirement ID → property labels falls out of extraction.

In generated Verilog a property's label is its name with `-` and `.` replaced by `_`:
`UTX-RST-001.tx` becomes `UTX_RST_001_tx`. Labels containing a double underscore are reserved
for the compiler's own checks (`__overlap`, `__range`, `__fired`); never write one in a spec.

### What happens to the Acceptance line

**A requirement has an emet block or an Acceptance line, never both.**

- **Statement** stays, unchanged and prose: it says what the block does.
- Where the check is a property of the block's clocked interface, the emet block *is* the
  check and there is no Acceptance line. Two normative statements of one check drift; one does
  not.
- Where emet cannot express the check — a pin map, a synthesis or flow constraint, a
  requirement about what the *harness* may not assume (`UTX-FRM-002`) — the prose
  **Acceptance** line stays and there is no emet block.

A requirement with neither, or with both, is a spec bug; the reviewer treats it as one.

Requirements written before emet still carry Acceptance lines. They are converted file by
file; until a file is converted, its Acceptance lines are its checks.

## The execution model

Everything below is stated in the cycle-exact terms of `spec/README.md`: *edge e* is the e-th
rising edge of the unit's clock, and the *value at edge e* of an expression is the value it
takes from the values its signals have at edge e — the values a flip-flop clocked by that edge
captures. emet never looks backwards; there is no `$past`.

**One clock.** A unit has one clock, named in its `unit` block, and every check happens at its
rising edge. Multi-clock properties are out of scope for v0.

**The trace starts at edge 1.** No check and no firing happens at edge 1: nothing in the unit
has been clocked yet. Every property is live from edge 2 on.

**Firings.** `at`, `within`, `hold` and `stable` have a *trigger*: a boolean expression. The
property *fires* at every edge k ≥ 2 at which the trigger is true. A firing carries:

- `$n` — the value of the pattern's count expression at edge k, latched. It never changes
  during the firing, so `$n` is a property of edge k and not of the signals it was computed
  from. `at`, `within` and `hold` have a count; `stable` does not, and has no `$n`.
- `$t` — the number of edges since the firing edge: at edge k+j, `$t` is j. `$t` is 1 at the
  first edge of the firing's window.
- one register per `sample` declaration, holding that expression's value at edge k.

`$t` and `$n` exist in `at`, `within` and `hold`. `stable` has neither: its window is bounded
by a release condition and not by a count, so there is nothing to count towards.

`$t`, `$n` and the samples are what make "the frame in progress ignores later input changes"
a consequence of the language rather than a separate requirement.

**Reset cancels a firing.** The `unit` block may name a reset expression. A firing started at
edge k is *cancelled* at the first edge j > k at which the reset is true: nothing is checked at
edge j or after it for that firing, and it is not a failure. This is what "and no `clear`" in a
requirement's statement compiles to.

A trigger fires normally at an edge where the reset is true — otherwise a property *about* the
reset (`UTX-RST-001`, whose trigger is `clear` itself) could never fire. So a trigger that is
meaningless during reset must say so: write `&& !clear` into it. Conventionally the unit's
`let accept = valid && ready && !clear;` carries it once for everyone.

**One firing at a time.** `at`, `within` and `hold` track exactly one firing. A trigger that
is true while a firing of the same property is still outstanding fails the compiler-generated
check `<LABEL>__overlap`. A firing that *retires* at edge j — reaches its check edge, is
discharged early, or is cancelled by reset at j — does not conflict with a trigger at edge j,
so back-to-back triggers at the earliest legal edge are fine (`UTX-HSK-003` relies on this).

Overlap is a failure and not a silent weakening: a design where the trigger really can overlap
cannot be checked by that pattern, and the property must be split or its trigger qualified
until it cannot. `stable` is the exception: a trigger during a live firing re-arms it with the
value the firing already requires the expression to have, which can neither weaken nor
contradict it, so `stable` has no `__overlap` check.

## Units, properties, declarations

### The unit block

```emet
unit UTX golem_uart_tx {
  clock clock;
  reset clear;

  in  clear   1;
  in  data    8;
  in  valid   1;
  in  divisor 16;
  out tx      1;
  out ready   1;

  let accept = valid && ready && !clear;
}
```

- `unit <NAME> <verilog-module>` — `<NAME>` is the block's requirement-ID prefix (`UTX`) and
  `<verilog-module>` is the module the monitor watches.
- `clock <port>;` — the clock. Required; implicitly a 1-bit input.
- `reset <expr>;` — the reset condition, in terms of the unit's ports. Optional; without it no
  firing is ever cancelled.
- `in`/`out <port> <width>;` — one line per row of the interface table, widths in bits,
  scalars are width 1. `in` and `out` are both inputs of the monitor; the direction is there so
  the block and the table can be read against each other. They must agree: the table is what a
  human reads, this block is what the compiler reads, and a mismatch is a spec bug.
- `let <name> = <expr>;` — a named abbreviation, available to every property in the file.

Exactly one `unit` block per block spec, and every property in that file attaches to it.

### The property block

```emet
property UTX-HSK-002 {
  sample T = divisor + 1;
  hold 10 * T after accept: !ready;
  cover shortest_bit: T == 1;
}
```

A property block contains, in this order:

1. any number of `let` and `sample` declarations,
2. at most one pattern statement,
3. any number of `cover` directives.

- `let <name> = <expr>;` — an abbreviation local to the property. Unlike a `sample` it is
  combinational: it takes the value its signals have at the edge where it is used.
- `sample <name> = <expr>;` — latched at the firing edge (above). Legal only in a property
  whose pattern has a trigger. A `sample` may refer to a `let`, to a unit-level `let` and to a
  sample declared before it, but never to `$t` or `$n`.
- A block with no pattern statement is a **cover-only** block: its covers are evaluated at
  every edge from edge 2 on. This is how a requirement asks for a directed scenario without
  asserting anything new.

A `let` or `sample` name must differ from every port name, every unit-level `let` and every
other name in scope. Names are `[A-Za-z_][A-Za-z0-9_]*`.

### Grammar

Whitespace and newlines are insignificant; every statement ends in `;`. A comment runs from
`//` to the end of the line. The whole of emet v0:

```
block       ::= { unit | property }

unit        ::= "unit" ident ident "{" { unit-decl } "}"
unit-decl   ::= "clock" ident ";"
              | "reset" expr ";"
              | ("in" | "out") ident integer ";"
              | let-decl

property    ::= "property" prop-name "{" { let-decl | sample-decl } [ pattern ] { cover } "}"
let-decl    ::= "let" ident "=" expr ";"
sample-decl ::= "sample" ident "=" expr ";"

pattern     ::= "invariant" expr ";"
              | "at"     count "after" expr ":" expr ";"
              | "within" count "after" expr ":" expr ";"
              | "hold"   count "after" expr ":" expr ";"
              | "stable" expr "after" expr "until" expr ";"
              | ("onehot" | "mutex") "{" expr { "," expr } "}" ";"
cover       ::= "cover" tag ":" expr ";"
count       ::= expr

prop-name   ::= req-id [ "." tag ]
req-id      ::= upper{2,4} "-" upper{2,4} "-" digit{3}     // spec/README.md convention
tag         ::= (lower | digit | "_")+
ident       ::= (letter | "_") { letter | digit | "_" }
```

Keywords — `unit`, `property`, `clock`, `reset`, `in`, `out`, `let`, `sample`, `invariant`,
`at`, `within`, `hold`, `stable`, `after`, `until`, `onehot`, `mutex`, `cover` — are reserved
and cannot name a port, a `let` or a `sample`. The one exception is the clock: a port named
`clock` is fine, because no expression ever mentions it. `$t` and `$n` are reserved too, and
are unreachable as identifiers: an emet identifier cannot begin with `$`.

## Expressions

An emet expression is a Verilog-2005 expression restricted to what a monitor can evaluate
combinationally, plus one operator Verilog does not have.

**Operands**: port names, `let` and `sample` names, `$t`, `$n`, and Verilog integer literals
(sized or unsized, any base).

**Operators**, Verilog-2005 precedence: `~ ! & | ^ && || == != < <= > >= + - * / % ?:`,
concatenation `{a, b}` and replication `{n{a}}`, bit-select `a[i]` and constant part-select
`a[i:j]`, and implication `->`.

- `a -> b` is implication. It binds looser than everything else and is right-associative;
  parenthesise it inside a larger expression. Verilog has no binary `->` in expressions, so
  nothing is being redefined; the compiler emits `(!(a) || (b))`.
- Not available: `===`, `!==`, `<<`, `>>`, function calls, system functions, `$past`. The
  x-sensitive comparisons are out because formal has no x; the shifts are out because they
  wrap silently and `*` says what is meant.

**Values are unsigned integers.** There are no signed values and no negative numbers.

**Arithmetic does not wrap.** The compiler widens operands so that every intermediate result
fits exactly: `a + b` takes max(wa,wb)+1 bits, `a * b` takes wa+wb, comparisons zero-extend to
the wider operand. `T = divisor + 1` with a 16-bit `divisor` is 17 bits wide and reaches 65536,
as `spec/uart_tx.md` says it must. `/` and `%` are floor division and remainder on
non-negative integers. For every subtraction in a property the compiler emits a `__range`
check, live in the same window as the property's own check, that the left operand is at least
the right: `$t - 1` may not underflow silently.

**Conditions are one bit.** The expression in an `invariant`, a trigger, a release, a pattern
body, an `onehot`/`mutex` entry or a `cover` must be 1 bit wide. Compare wider expressions
explicitly: `invariant state` is a compiler error, `invariant state == 3'd2` is a property.

**Counts are at least 1.** A count expression may mention ports, `let`s and `sample`s — all
evaluated at the firing edge, so the compiler substitutes a sample's defining expression there
— but never `$t` or `$n`. The compiler emits `<LABEL>__range` at the firing edge for
`count >= 1`. Offset 0 is not a count; it is an `invariant`.

## The six patterns

Each pattern below gives its syntax, its meaning in edges, and the shape of the Verilog the
compiler emits. Counts and offsets are in clock cycles throughout.

Three things are shared by every monitor and are written once per module:

```verilog
  reg emet_started = 1'b0;               // 0 at edge 1, 1 from edge 2 on
  always @(posedge clock) emet_started <= 1'b1;
  wire emet_reset = clear;               // the unit's `reset` expression, or 1'b0
```

and every check, whatever the pattern, is emitted as one `always` block over a *window* W (the
edges at which the check applies) and a *condition* C:

```verilog
`ifdef EMET_SIM
  reg LABEL_fail = 1'b0;                 // sticky, one per check
  always @(posedge clock)
    if (W) if ((C) !== 1'b1) begin
      $display("emet: LABEL failed at edge %0d (%0t)", emet_edge, $time);
      LABEL_fail <= 1'b1;
    end
`else
  always @(posedge clock) if (W) LABEL: assert (C);
`endif
```

The sim form tests `!== 1'b1` rather than `!C`, so a condition that is x is a failure and not
a silent pass. Only the window and the condition differ between patterns, so only those are
given below. The compiler's own checks — `__overlap`, `__range` — are checks like any other
and take this same dual form; they are written as bare asserts in the monitor sketches below
only to keep them short.

### 1. invariant

```emet
invariant <cond>;
```

`<cond>` is true at every edge e ≥ 2, including edges at which the reset is true: an invariant
has no firing, so there is nothing for the reset to cancel. An invariant that is only meant to
hold out of reset says so: `invariant !clear -> ...`.

- W = `emet_started`, C = `<cond>`.

### 2. at — implication at a fixed cycle offset

```emet
at <count> after <trigger>: <cond>;
```

For every firing at edge k, with N the value of `<count>` at edge k: `<cond>` is true at edge
k+N, unless the firing is cancelled first. Nothing is claimed about edges k+1 .. k+N-1.

```verilog
  reg [Wn-1:0] L_t = 0, L_n = 0;         // $t, $n; Wn holds the largest value <count> can take
  reg          L_busy = 1'b0;
  reg [Ws-1:0] L_s_<name>;               // one per `sample`, Ws its expression's width
  wire L_live   = L_busy && !emet_reset;
  wire L_retire = L_busy && (emet_reset || L_t == L_n);
  wire L_fire   = emet_started && (<trigger>);

  always @(posedge clock) begin
    if (L_retire)     L_busy <= 1'b0;
    else if (L_busy)  L_t    <= L_t + 1'b1;
    if (L_fire) begin
      L_busy <= 1'b1;
      L_t    <= 1;
      L_n    <= (<count>);               // samples substituted by their expressions
      L_s_<name> <= (<sample expr>);
    end
    L__overlap: assert (!(L_fire && L_busy && !L_retire));
    L__range:   assert (!L_fire || (<count>) >= 1);
  end
```

- W = `L_live && L_t == L_n`, C = `<cond>`.

The counter is as wide as the largest value `<count>` can take. The firing's registers are
what `$t`, `$n` and the sample names mean inside `<cond>`.

### 3. within — bounded response (a deadline)

```emet
within <count> after <trigger>: <cond>;
```

For every firing at edge k, with N the value of `<count>` at edge k: `<cond>` is true at at
least one of the edges k+1 .. k+N. The firing is *discharged* at the first such edge, so a new
trigger may fire there. Cancelled by reset as usual.

Same firing block as `at`, with the discharge folded into the retirement:

```verilog
  wire L_hit    = L_live && (<cond>);
  wire L_retire = L_busy && (emet_reset || L_hit || L_t == L_n);
```

- W = `L_live && L_t == L_n`, C = `<cond>`.

The window is the same as `at`'s: at the deadline edge the response must be there. The
difference between the two patterns is the early discharge — `at` says *exactly then*,
`within` says *by then at the latest*.

### 4. hold — hold-for-n

```emet
hold <count> after <trigger>: <cond>;
```

For every firing at edge k, with N the value of `<count>` at edge k: `<cond>` is true at every
edge k+1 .. k+N, up to but not including the edge at which the firing is cancelled. `<cond>`
may use `$t` (1 .. N) to say something different at different edges of the window.

Same firing block as `at`.

- W = `L_live`, C = `<cond>`.

### 5. stable ... until

```emet
stable <expr> after <trigger> until <release>;
```

For every firing at edge k, let V be the value of `<expr>` at edge k. `<expr>` equals V at
every edge k+1 .. j, where j is the first edge after k at which `<release>` is true — the
release edge included. If `<release>` is never true the requirement runs to the end of the
trace, and a trace that ends with the firing outstanding is not a failure: `stable` is a safety
pattern, and a deadline is `within`.

A trigger during a live firing re-arms it (no `__overlap`), which is how "stays stable from
whenever it last became that, until the release" is written without looking backwards.

```verilog
  reg          L_busy = 1'b0;
  reg [Wv-1:0] L_v;
  wire L_live   = L_busy && !emet_reset;
  wire L_retire = L_busy && (emet_reset || (<release>));
  always @(posedge clock) begin
    if (L_retire) L_busy <= 1'b0;
    if (emet_started && (<trigger>)) begin
      L_busy <= 1'b1;
      L_v    <= (<expr>);
    end
  end
```

- W = `L_live`, C = `(<expr>) == L_v`.

`<expr>` may be any width; `stable` is the one pattern whose subject is not a condition.

### 6. onehot / mutex — one-hot and mutual exclusion

```emet
onehot { <cond>, <cond>, ... };
mutex  { <cond>, <cond>, ... };
```

At every edge e ≥ 2, exactly one (`onehot`) or at most one (`mutex`) of the listed conditions
is true. Two or more entries; each is one bit. Like `invariant`, these have no firing and the
reset does not cancel them.

```verilog
  wire [K-1:0] L_bits = { (<condK>), ..., (<cond1>) };
```

- `onehot`: W = `emet_started`, C = `L_bits != 0 && (L_bits & (L_bits - 1)) == 0`.
- `mutex`:  W = `emet_started`, C = `(L_bits & (L_bits - 1)) == 0`.

A one-hot over the bits of a vector is written as a list of bit-selects; emet has no vector
form.

## The cover directive

```emet
cover <tag>: <cond>;
```

`cover` asks for a witness, never for a guarantee: it fails nothing. Its label is
`<LABEL>_cover_<tag>`. In a triggered property a cover is evaluated at every edge at which the
firing is *outstanding* — `L_busy`, which unlike `L_live` includes the edge where a reset
cancels it — so it may use `$t`, `$n` and samples, and so "the reset arrived mid-frame" is a
scenario one can ask to see. In a cover-only or untriggered block a cover is evaluated at every
edge from edge 2 on.

- Formal: W = the property's cover window (`L_busy`, or `emet_started`), and the compiler
  emits `LABEL_cover_<tag>: cover (<cond>);`. The `cover` task of the block's SymbiYosys job
  is what proves the witness exists.
- Simulation: the same window sets a sticky `reg LABEL_cover_<tag>_hit`, which the cocotb test
  reads hierarchically to report which scenarios a run actually exercised.

**Non-vacuity is automatic.** For every property the compiler also emits `<LABEL>__fired`,
which covers the property doing real work, so a property that can never fire is caught without
anyone remembering to write a cover:

| Pattern              | `__fired` covers                          |
|----------------------|-------------------------------------------|
| `at`, `hold`         | `L_live && L_t == L_n` — a full window    |
| `within`             | `L_live && (<cond>)` — a response arrives |
| `stable`             | `L_live && (<release>)` — a release       |
| `invariant A -> B`   | `A` — the antecedent is reachable         |
| other `invariant`, `onehot`, `mutex` | nothing               |

Hand-written covers are for the scenarios that matter to a reader — back-to-back frames, the
shortest bit period, a reset in the middle of one — not for repeating this.

## The compiled monitor

One unit compiles to one module, `emet_<unit>` lower-cased (`emet_utx`), in one file. Its
ports are the unit's clock and every port of the unit, all inputs, in declaration order, plus
one output:

```verilog
// Generated by the emet compiler from spec/uart_tx.md. Do not edit.
`default_nettype none
module emet_utx (
    input  wire        clock,
    input  wire        clear,
    input  wire [7:0]  data,
    input  wire        valid,
    input  wire [15:0] divisor,
    input  wire        tx,
    input  wire        ready,
    output wire        emet_fail
);
```

- The monitor never instantiates the unit. Both harnesses wire it to the same nets the unit's
  instance is on, which is what makes one monitor serve both.
- `emet_fail` is the simulation verdict: under `EMET_SIM` it is the OR of every check's own
  sticky `<LABEL>_fail` flag, so it goes high at the first failing edge and stays high, and
  cocotb can read the individual flags to name the property. Without `EMET_SIM` it is tied to
  0 — formal reports failures as assertion traces.
- `` `ifdef EMET_SIM `` selects the simulation form of every check. Undefined — the default —
  gives the immediate-assert form that SymbiYosys reads. The `EMET_SIM` build also has a
  32-bit `emet_edge` counter whose value at edge e is e, so a simulation failure reports the
  same edge number the spec talks about.
- Unit-level `let`s become `wire`s; property-level `let`s become wires prefixed with the
  property's label; every firing register is prefixed with the property's label. Every
  identifier the compiler invents begins with `emet_` or a property label, so a monitor can
  never collide with the unit it watches.

The two harnesses are the verifier's lane; what the language fixes is the contract:

- **Formal**: the `.sby` harness instantiates the unit and `emet_<unit>` on the same nets. The
  `prove` task proves the asserts; the `cover` task reaches the covers.
- **Simulation**: `tb.v` instantiates `emet_<unit>` on the same nets and the test fails if
  `emet_fail` is ever 1.

## Style — so that two readers write the same property

1. **Say it forwards.** emet has no `$past`; every temporal claim starts at a trigger and looks
   forward. "X after Y" is a trigger on Y, never a look-back from X.
2. **One observable per property.** Split `tx && ready` into `.tx` and `.ready` so a
   counterexample names which one broke.
3. **Offset 0 is an `invariant`,** never `at 0` (which is a `__range` failure): a claim about
   the same edge is `invariant A -> B`.
4. **Put the reset in the trigger** of everything except a property about the reset itself, and
   prefer a unit-level `let` (`accept`) to repeating the qualification.
5. **Latch with `sample`, not with prose.** Anything the requirement says is fixed at the
   trigger edge — a bit period, a byte, a length — is a `sample`.
6. **Prefer comparisons to division.** `$t <= 2*T` is a comparator; `($t - 1) / T` is a
   divider, and a divider by a runtime value puts an unbounded proof out of reach. Multiply the
   constant, do not divide the counter.
7. **Name counts as the spec names them.** If the requirement says `10T`, write `10 * T`, not
   the expanded `10 * divisor + 10`.
8. **Cover the interesting trace, not the trigger.** `__fired` already covers the trigger.

## Limitations of v0

Named so that no one has to guess whether they exist:

- No `assume`, no input constraints, no environment model.
- No `$past` and no look-back operators; no `rose`/`fell`.
- One clock per unit; no clock-domain-crossing properties.
- No liveness: every pattern is a safety property, and "eventually" is `within` with a
  deadline.
- No overlapping firings for `at`, `within` and `hold` — the overlap is reported, not tracked.
- No auxiliary state machines. A requirement that needs a reference model to state its check
  is either decomposable into these six patterns (`$t` plus `sample`s reach further than they
  look — see `UTX-FRM-001`) or it keeps a prose Acceptance line and a hand-written monitor.
- `onehot`/`mutex` take a list of conditions, not a vector.
- Properties are per-unit; there is no way to relate two units' signals.

## Worked examples: every requirement of `spec/uart_tx.md`

These are illustrations — `spec/uart_tx.md` still carries its Acceptance lines until it is
converted — but they are the properties that conversion should produce, and between them they
use every pattern.

```emet
unit UTX golem_uart_tx {
  clock clock;
  reset clear;

  in  clear   1;
  in  data    8;
  in  valid   1;
  in  divisor 16;
  out tx      1;
  out ready   1;

  // spec/uart_tx.md "Definitions": the accept edge.
  let accept = valid && ready && !clear;
}
```

**UTX-RST-001 — Reset state.** The one property whose trigger is the reset itself. A firing is
cancelled if `clear` is still true at the next edge, so the check lands on the first edge after
the *last* clear edge — exactly the requirement's "first edge after an edge where `clear = 1`
was sampled".

```emet
property UTX-RST-001.tx    { at 1 after clear: tx; }
property UTX-RST-001.ready { at 1 after clear: ready; }
```

**UTX-IDL-001 — Idle line is high.**

```emet
property UTX-IDL-001 { invariant ready -> tx; }
```

**UTX-HSK-001 — Single acceptance.** `valid` while `ready = 0` is not queued, so the line must
not move while the block is idle: `tx` is stable from any idle edge through the next accept
edge, and the start bit can only appear at the edge after one.

```emet
property UTX-HSK-001 {
  stable tx after (ready && !accept && !clear) until accept;
}
```

**UTX-HSK-002 — Busy during a frame.** `ready = 0` at k+1 .. k+10T.

```emet
property UTX-HSK-002 {
  sample T = divisor + 1;
  hold 10 * T after accept: !ready;
  cover shortest_bit: $t == $n && T == 1;
}
```

**UTX-HSK-003 — Ready after the frame.** `ready = 1` at k+10T+1 exactly. The firing retires at
that edge, so the back-to-back accept the requirement permits there is not an overlap.

```emet
property UTX-HSK-003 {
  sample T = divisor + 1;
  at 10 * T + 1 after accept: ready;
}
```

**UTX-HSK-004 — Ready holds while idle.** The same shape as UTX-HSK-001 on the other output.
Each idle edge re-arms the firing, so `ready` is pinned high from wherever it last went high
through the next accept edge.

```emet
property UTX-HSK-004 {
  stable ready after (ready && !accept && !clear) until accept;
}
```

**UTX-FRM-001 — Frame waveform.** `tx = F[(n-1) div T]` at edge k+n for n = 1 .. 10T. The
division is written as a comparison chain: bit i applies while `i*T < $t <= (i+1)*T`.

```emet
property UTX-FRM-001 {
  sample T = divisor + 1;
  sample F = {1'b1, data, 1'b0};      // F[0] start, F[1..8] data LSB first, F[9] stop
  hold 10 * T after accept:
    tx == ($t <= 1*T ? F[0] :
           $t <= 2*T ? F[1] :
           $t <= 3*T ? F[2] :
           $t <= 4*T ? F[3] :
           $t <= 5*T ? F[4] :
           $t <= 6*T ? F[5] :
           $t <= 7*T ? F[6] :
           $t <= 8*T ? F[7] :
           $t <= 9*T ? F[8] :
                       F[9]);
  cover byte_a5: $t == $n && F == 10'b1_1010_0101_0;
  cover clear_midframe: $t > 4*T && clear;
}
```

**UTX-FRM-002 — Inputs latched at acceptance.** No emet block: the requirement says the
properties above hold with `data`, `divisor` and `valid` unconstrained after the accept edge,
which is a statement about what the harness may not assume. emet has no `assume`, so there is
nothing to write and nothing that could weaken it — `sample` is the mechanism, and this
requirement keeps its prose **Acceptance** line as the standing prohibition on adding one.

**Patterns not exercised by the UART.** `within` and `onehot`/`mutex` have no use in a block
this small; they first appear in the host SPI link and the sequencer, and would read like this
(the IDs are invented — neither block is specified yet):

```emet
// "The chip answers a read within 8 cycles of the command byte" — a deadline.
property SPI-RSP-001 { within 8 after cmd_done: resp_valid; }

// "The sequencer is in exactly one of fetch, wait, execute" — an encoding invariant.
property SEQ-STE-001 { onehot { st_fetch, st_wait, st_exec }; }
```
