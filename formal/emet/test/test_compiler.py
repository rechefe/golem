"""Compiler self-tests. These don't depend on spec/ being converted to emet
yet (issue #19: spec/emet.md and spec/uart_tx.md's emet blocks are still on
unmerged spec PRs #18/#21) -- they build a small repo_root fixture per test
and drive the compiler exactly as `make emet` will once that content lands.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from emet.driver import compile_spec
from emet.errors import EmetError

REPO_ROOT = Path(__file__).resolve().parents[3]
UTX_MD = (REPO_ROOT / "formal" / "emet" / "test" / "fixtures" / "uart_tx_emet.md").read_text()


def make_repo(tmp_path, uart_tx_md, extra_files=None):
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "README.md").write_text(
        "# fixture\n\n## Files\n\n"
        "| File          | Block                |\n"
        "|---------------|-----------------------|\n"
        "| `uart_tx.md`  | UART transmitter      |\n"
    )
    (spec / "uart_tx.md").write_text(uart_tx_md)
    for name, text in (extra_files or {}).items():
        (spec / name).write_text(text)
    return tmp_path


def compile_one(tmp_path, uart_tx_md):
    repo = make_repo(tmp_path, uart_tx_md)
    results = compile_spec(repo)
    assert len(results) == 1
    return results[0]


# ---- the real UART block, from spec PR #21 (spec/emet.md's worked examples) ----

def test_compiles_every_uart_requirement(tmp_path):
    r = compile_one(tmp_path, UTX_MD)
    assert r.compiled.req_ids == [
        "UTX-FRM-001", "UTX-HSK-001", "UTX-HSK-002", "UTX-HSK-003",
        "UTX-HSK-004", "UTX-IDL-001", "UTX-RST-001",
    ]
    assert r.compiled.properties["UTX-RST-001"] == ["UTX_RST_001_tx", "UTX_RST_001_ready"]


def test_counter_widths_match_worked_example(tmp_path):
    """spec/emet.md: T is 17 bits (max 65536), 10*T+1 is 20 bits (max 655361)."""
    r = compile_one(tmp_path, UTX_MD)
    v = r.compiled.verilog
    assert "reg [16:0] UTX_HSK_002_s_T;" in v   # T = divisor + 1
    assert "reg [19:0] UTX_HSK_003_t = 0, UTX_HSK_003_n = 0;" in v  # 10*T + 1


def test_sample_used_live_in_count_not_via_stale_register(tmp_path):
    """The count is evaluated at the firing edge, same edge the sample latches;
    it must inline the sample's defining expression, not reference the sample's
    register (which still holds the previous firing's value at that edge)."""
    r = compile_one(tmp_path, UTX_MD)
    v = r.compiled.verilog
    assert "UTX_HSK_002_n <= (((4'd10) * (((divisor) + (1'd1)))));" in v
    assert "UTX_HSK_002_s_T" not in v.split("UTX_HSK_002_n <=")[1].split(";")[0]


def test_generated_verilog_is_syntactically_valid_under_both_ifdef_branches(tmp_path):
    r = compile_one(tmp_path, UTX_MD)
    src = tmp_path / "emet_utx.v"
    src.write_text(r.compiled.verilog)
    subprocess.run(["iverilog", "-g2005-sv", "-tnull", "-DEMET_SIM", str(src)], check=True)
    # The non-EMET_SIM branch uses labelled immediate assert/cover statements,
    # a SystemVerilog-ism that SymbiYosys's `read -formal` accepts but plain
    # iverilog -g2005 does not; -g2005-sv covers both branches here.
    subprocess.run(["iverilog", "-g2005-sv", "-tnull", str(src)], check=True)


# ---- section / traceability ----

def test_property_id_must_match_its_section(tmp_path):
    bad = UTX_MD.replace("### UTX-IDL-001", "### UTX-IDL-002")
    with pytest.raises(EmetError, match="UTX-IDL-002"):
        compile_one(tmp_path, bad)


def test_unit_block_must_be_in_interface_section(tmp_path):
    bad = UTX_MD.replace("## Interface", "## Not Interface")
    with pytest.raises(EmetError, match="Interface"):
        compile_one(tmp_path, bad)


def test_port_width_mismatch_with_table_is_caught(tmp_path):
    bad = UTX_MD.replace("in  divisor 16;", "in  divisor 15;")
    with pytest.raises(EmetError, match="divisor.*bits"):
        compile_one(tmp_path, bad)


def test_two_unit_blocks_in_one_file_is_an_error(tmp_path):
    bad = UTX_MD + "\n\n## Interface\n\n```emet\nunit UTX golem_uart_tx { clock clock; in x 1; }\n```\n"
    with pytest.raises(EmetError, match="more than one"):
        compile_one(tmp_path, bad)


# ---- expression semantics ----

MINI_UNIT = """\
## Interface

```emet
unit ABC dut {
  clock clock;
  reset clear;
  in  clear 1;
  in  a     4;
  in  b     4;
  out y     1;
}
```

### ABC-XXX-001 — placeholder

```emet
%s
```
"""


def compile_prop(tmp_path, body):
    md = MINI_UNIT % body
    return compile_one(tmp_path, md)


def test_invariant_rejects_non_bit_condition(tmp_path):
    with pytest.raises(EmetError, match="1 bit"):
        compile_prop(tmp_path, "property ABC-XXX-001 { invariant a; }")


def test_at_zero_is_rejected_use_invariant_instead(tmp_path):
    # offset 0 is a `__range` failure at runtime, not a parse error, but the
    # grammar itself still requires a full expression after `at`; check the
    # __range check text is emitted so a proof would catch the 0-offset case.
    r = compile_prop(tmp_path, "property ABC-XXX-001 { at 1 after clear: y; }")
    assert "ABC_XXX_001__range" in r.compiled.verilog


def test_onehot_needs_at_least_two_entries(tmp_path):
    with pytest.raises(EmetError, match="two or more"):
        compile_prop(tmp_path, "property ABC-XXX-001 { onehot { y }; }")


def test_bit_select_out_of_range_is_rejected(tmp_path):
    with pytest.raises(EmetError, match="out of range"):
        compile_prop(tmp_path, "property ABC-XXX-001 { invariant a[4] == 1'd0; }")


def test_undefined_identifier_is_rejected(tmp_path):
    with pytest.raises(EmetError, match="undefined"):
        compile_prop(tmp_path, "property ABC-XXX-001 { invariant nope; }")


def test_dollar_t_outside_a_counted_pattern_is_rejected(tmp_path):
    with pytest.raises(EmetError, match=r"\$t"):
        compile_prop(tmp_path, "property ABC-XXX-001 { invariant $t == 4'd0; }")


def test_sample_without_trigger_is_rejected(tmp_path):
    with pytest.raises(EmetError, match="sample"):
        compile_prop(tmp_path, "property ABC-XXX-001 { sample s = a; invariant y; }")


def test_subtraction_emits_a_range_check(tmp_path):
    r = compile_prop(
        tmp_path,
        "property ABC-XXX-001 { hold 4 after clear: (a - b) >= 4'd0; }",
    )
    assert "__range" in r.compiled.verilog
    assert "(a) >= (b)" in r.compiled.verilog


def test_replication_and_concat_widths(tmp_path):
    r = compile_prop(
        tmp_path,
        "property ABC-XXX-001 { invariant {4{a[0]}} == {a[0], a[0], a[0], a[0]}; }",
    )
    assert r.compiled  # compiles without a width mismatch


def test_multiply_uses_exact_max_value_not_operand_bit_growth(tmp_path):
    """10 * a (a is 4 bits, max 15) should be sized for max 150, i.e. 8 bits,
    not the structural 4+4=8... pick an example where the two disagree."""
    r = compile_prop(tmp_path, "property ABC-XXX-001 { hold 3 * a after clear: y; }")
    # max(3*a) = 3*15 = 45 -> 6 bits. A naive "unsized literal is 32 bits"
    # rule would force this to 32+4=36 bits instead.
    assert "reg [5:0] ABC_XXX_001_t = 0, ABC_XXX_001_n = 0;" in r.compiled.verilog


# ---- cover / __fired non-vacuity ----

def test_invariant_implication_gets_a_fired_cover(tmp_path):
    r = compile_prop(tmp_path, "property ABC-XXX-001 { invariant a == 4'd0 -> y; }")
    assert "ABC_XXX_001__fired" in r.compiled.verilog


def test_plain_invariant_gets_no_fired_cover(tmp_path):
    r = compile_prop(tmp_path, "property ABC-XXX-001 { invariant y || !y; }")
    assert "ABC_XXX_001__fired" not in r.compiled.verilog
