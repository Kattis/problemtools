#include "validator.h"


void run() {
  const bool nFive = Arg("nFive", 0);
  int N = Int(1, 10); Endl();
  if (nFive) assert(N == 5);
  for (int i = 0; i < N; i++) {
    string s = Line();
    for (auto it : s) {
      assert('a' <= it && it <= 'z');
    }
  }
  Eof();
}
