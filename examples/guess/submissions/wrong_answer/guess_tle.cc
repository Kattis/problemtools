#include <cstdio>
using namespace std;

// Test that if the validator says WA, that's the verdict given even if we
// TLE afterwards (realistically because we tried to read from stdin and didn't
// get a response we expected).

int main(void) {
    printf("-1\n");
    fflush(stdout);
    for (;;);
}
