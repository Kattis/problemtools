package main

import (
    "fmt"
    "io"
)

func abs(x int64) int64 {
    if x < 0 {
        return -x
    } else {
        return x
    }
}

func main() {
    var a, b int64

    for {
        _, err := fmt.Scanf("%d%d", &a, &b)
        if err == io.EOF {
            break
        }

        fmt.Printf("%d\n", abs(a - b))
    }
}
