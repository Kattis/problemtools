(* Get the i^th entry in the list, and convert it to an Int64. *)
let nth l i = (Int64.of_string (List.nth l i));;

try
    while true;
    do
        let line = read_line () in
        let tokens = Str.split (Str.regexp " ") line in
        let a = (nth tokens 0) in
        let b = (nth tokens 1) in
        let diff = Int64.abs (Int64.sub a b) in
            begin
                Printf.printf "%Ld\n" diff
            end;
    done;
with End_of_file -> ();;
