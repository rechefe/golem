(* Tiny Tapeout top level. Spec: spec/top.md requirements TOP-xxx. *)

open! Core
open! Hardcaml
open Signal

let module_name = "tt_um_rechefe_golem"

module I = struct
  type 'a t =
    { ui_in : 'a [@bits 8]
    ; uio_in : 'a [@bits 8]
    ; ena : 'a
    ; clk : 'a
    ; rst_n : 'a
    }
  [@@deriving hardcaml]
end

module O = struct
  type 'a t =
    { uo_out : 'a [@bits 8]
    ; uio_out : 'a [@bits 8]
    ; uio_oe : 'a [@bits 8]
    }
  [@@deriving hardcaml]
end

(* 115200 baud at 50 MHz: 434 cycles per bit (TOP-PIN-001). *)
let gate_divisor = 433

let create scope (i : _ I.t) : _ O.t =
  let uart =
    Uart_tx.hierarchical
      scope
      { Uart_tx.I.clock = i.clk (* TOP-CLK-001 *)
      ; clear = ~:(i.rst_n)
      ; data = i.ui_in
      ; valid = i.uio_in.:(0)
      ; divisor = of_int ~width:16 gate_divisor
      }
  in
  (* [ena] (always 1 while powered) and uio_in[7:1] are unused in the gate wiring. *)
  { O.uo_out = zero 6 @: uart.ready @: uart.tx
  ; uio_out = zero 8
  ; uio_oe = zero 8
  }
;;
