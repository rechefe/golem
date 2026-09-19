(* UART transmitter, 8N1, programmable bit period. Spec: spec/uart_tx.md requirements UTX-xxx. *)

open! Core
open! Hardcaml
open Signal

module I = struct
  type 'a t =
    { clock : 'a
    ; clear : 'a
    ; data : 'a [@bits 8]
    ; valid : 'a
    ; divisor : 'a [@bits 16]
    }
  [@@deriving hardcaml]
end

module O = struct
  type 'a t =
    { tx : 'a
    ; ready : 'a
    }
  [@@deriving hardcaml]
end

let create (scope : Scope.t) (i : _ I.t) : _ O.t =
  let ( -- ) = Scope.naming scope in
  let spec = Reg_spec.create ~clock:i.clock ~clear:i.clear () in
  let open Always in
  (* All registers clear to zero. [tx_n] is the inverted line, so clear gives an idle-high
     [tx] (UTX-RST-001) and [busy] = 0 gives [ready] = 1. *)
  let busy = Variable.reg spec ~width:1 in
  let tx_n = Variable.reg spec ~width:1 in
  let shift = Variable.reg spec ~width:8 in (* data bits not yet sent, LSB next *)
  let bit_index = Variable.reg spec ~width:4 in (* frame bit on the line: 0 start .. 9 stop *)
  let cycle = Variable.reg spec ~width:16 in (* cycles spent on the current bit *)
  let period = Variable.reg spec ~width:16 in (* T - 1, latched at accept (UTX-FRM-002) *)
  (* Readable names in the generated Verilog and in counterexample traces. *)
  List.iter
    [ busy, "busy"
    ; tx_n, "tx_n"
    ; shift, "shift"
    ; bit_index, "bit_index"
    ; cycle, "cycle"
    ; period, "period"
    ]
    ~f:(fun (v, name) -> ignore (v.value -- name : Signal.t));
  let end_of_bit = (cycle.value ==: period.value) -- "end_of_bit" in
  compile
    [ if_
        busy.value
        [ if_
            end_of_bit
            [ cycle <--. 0
            ; if_
                (bit_index.value ==:. 9)
                [ (* Stop bit done: back to idle, ready at edge k+10T+1 (UTX-HSK-003). *)
                  busy <--. 0
                ; tx_n <--. 0
                ]
                [ bit_index <-- bit_index.value +:. 1
                ; (* Next frame bit: data LSB first for bits 1..8, then stop = 1. *)
                  tx_n <-- ~:(mux2 (bit_index.value ==:. 8) vdd (lsb shift.value))
                ; shift <-- srl shift.value 1
                ]
            ]
            [ cycle <-- cycle.value +:. 1 ]
        ]
        [ (* Accept edge: valid while ready (UTX-HSK-001). Start bit goes out next edge. *)
          when_
            i.valid
            [ busy <--. 1
            ; tx_n <--. 1
            ; shift <-- i.data
            ; bit_index <--. 0
            ; cycle <--. 0
            ; period <-- i.divisor
            ]
        ]
    ];
  { O.tx = ~:(tx_n.value); ready = ~:(busy.value) }
;;

let hierarchical scope i =
  let module H = Hierarchy.In_scope (I) (O) in
  H.hierarchical ~scope ~name:"golem_uart_tx" create i
;;
