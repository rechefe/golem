(* Designer's unit tests for the UART transmitter (spec/uart_tx.md). *)

open! Core
open! Hardcaml
open! Hardcaml_waveterm
module Uart_tx = Golem.Uart_tx
module Sim = Cyclesim.With_interface (Uart_tx.I) (Uart_tx.O)

let create_sim () =
  let scope = Scope.create ~flatten_design:true () in
  Sim.create ~config:Cyclesim.Config.trace_all (Uart_tx.create scope)
;;

(* Clear, then send [data] with [divisor]; returns the sampled tx line, one char per edge,
   from the accept edge until ready returns. *)
let send ?(divisor = 0) sim data =
  let i : _ Uart_tx.I.t = Cyclesim.inputs sim in
  let o : _ Uart_tx.O.t = Cyclesim.outputs ~clock_edge:Before sim in
  i.clear := Bits.vdd;
  Cyclesim.cycle sim;
  i.clear := Bits.gnd;
  i.data := Bits.of_int ~width:8 data;
  i.divisor := Bits.of_int ~width:16 divisor;
  i.valid := Bits.vdd;
  Cyclesim.cycle sim;
  i.valid := Bits.gnd;
  let line = Buffer.create 64 in
  let rec loop n =
    Cyclesim.cycle sim;
    Buffer.add_char line (if Bits.to_bool !(o.tx) then '1' else '0');
    if Bits.to_bool !(o.ready) || n > 1000 then () else loop (n + 1)
  in
  loop 0;
  Buffer.contents line
;;

let%expect_test "0xA5 at T=1: start, data LSB first, stop, then ready (UTX-FRM-001, UTX-HSK-003)" =
  print_endline (send (create_sim ()) 0xA5);
  (* start=0, A5 LSB-first=10100101, stop=1, then the idle edge where ready returns. *)
  [%expect {| 01010010111 |}]
;;

let%expect_test "T=3 stretches every bit to 3 cycles (UTX-FRM-001)" =
  print_endline (send ~divisor:2 (create_sim ()) 0x0F);
  [%expect {| 0001111111111110000000000001111 |}]
;;

let%expect_test "waveform of a 0x5A frame at T=2" =
  let sim = create_sim () in
  let waves, sim = Waveform.create sim in
  ignore (send ~divisor:1 sim 0x5A : string);
  Waveform.print ~display_width:90 ~display_height:18 ~wave_width:0 waves;
  [%expect {|
    ┌Signals───────────┐┌Waves───────────────────────────────────────────────────────────────┐
    │clock             ││┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐┌┐│
    │                  ││ └┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└┘└│
    │clear             ││──┐                                                                 │
    │                  ││  └───────────────────────────────────────────                      │
    │                  ││──┬───────────────────────────────────────────                      │
    │data              ││ .│5A                                                               │
    │                  ││──┴───────────────────────────────────────────                      │
    │                  ││──┬───────────────────────────────────────────                      │
    │divisor           ││ .│0001                                                             │
    │                  ││──┴───────────────────────────────────────────                      │
    │valid             ││  ┌─┐                                                               │
    │                  ││──┘ └─────────────────────────────────────────                      │
    │ready             ││────┐                                       ┌─                      │
    │                  ││    └───────────────────────────────────────┘                       │
    │tx                ││────┐       ┌───┐   ┌───────┐   ┌───┐   ┌─────                      │
    │                  ││    └───────┘   └───┘       └───┘   └───┘                           │
    └──────────────────┘└────────────────────────────────────────────────────────────────────┘
    |}]
;;
