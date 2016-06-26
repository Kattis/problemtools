/* Incorrect solution for "A Different Problem" (uses 32-bit ints
 * instead of 64-bit ints)
 */
#include <cstdio>
#include <algorithm>

int main(void) {
    int a, b;
    while (scanf("%d%d", &a, &b) == 2)
        printf("%d\n", std::abs(a-b));
    return 0;
}
