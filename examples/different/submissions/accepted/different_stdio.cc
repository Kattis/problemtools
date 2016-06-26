#include <cstdio>
#include <algorithm>

int main(void) {
    long long a, b;
    while (scanf("%lld%lld", &a, &b) == 2)
        printf("%lld\n", std::abs(a-b));
    return 0;
}
