#include <iostream>
#include <algorithm>

int main(void) {
  char *buf = new char[512*1024*1024]; // 512MB
  buf[0] = 0;
  for (int i = 1; i < 512*1024*1024; ++i)
      buf[i] = 23*buf[i-1]+42;
  std::cout << "Hello World!\n" << std::endl;
  return 0;
}
