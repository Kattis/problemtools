/* Incorrect solution for "A Different Problem" (does not take absolute value)
 */
#include <cstdio>

int main(void) {
    long long a, b;
    while (scanf("%lld%lld", &a, &b) == 2)
        printf("%lld\n", a-b);
    return 0;
}
