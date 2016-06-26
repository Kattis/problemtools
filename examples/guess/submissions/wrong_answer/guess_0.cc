#include <cstdio>
#include <cstring>

int main(void) {
    int lo = 0, hi = 1023;
    while (true) {
        int m = (lo+hi)/2;
        printf("%d\n", m);
        fflush(stdout);
        char res[1000];
        scanf("%s", res);
        if (!strcmp(res, "correct")) break;
        if (!strcmp(res, "lower")) hi = m-1;
        else lo = m+1;
    }
    return 0;
}
