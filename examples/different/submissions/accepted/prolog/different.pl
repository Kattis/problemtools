[kattio].

main :-
    repeat,
    read_int(X), read_int(Y),
    (X == end_of_file ;
     solve(X, Y),
     fail
    ).

solve(X, Y) :-
    Z is abs(X-Y),
    write(Z), nl.
