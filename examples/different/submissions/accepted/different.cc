#include <iostream>
#include <algorithm>

int main(void) {
    long long a, b;
    while (std::cin >> a >> b)
        std::cout << std::abs(a-b) << std::endl;
    return 0;
}
