#include <cstdio>
#include <cstring>
#include <cstdlib>

int main(void) {
    int lo = 1, hi = 1000;
    while (true) {
        int m = lo + random() % (hi-lo+1);
        printf("%d\n", m);
        fflush(stdout);
        char res[1000];
        if (scanf("%s", res) != 1) break;
        if (!strcmp(res, "correct")) break;
        if (!strcmp(res, "lower")) hi = m-1;
        else lo = m+1;
    }
    return 0;
}
