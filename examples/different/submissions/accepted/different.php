<?php

while (fscanf(STDIN, '%d%d', $number1, $number2) === 2) {
    $res = abs($number1 - $number2);
    fprintf(STDOUT, "%d\n", $res);
}
