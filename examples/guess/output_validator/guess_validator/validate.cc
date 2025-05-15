#include <utility>
#include <string>
#include <cassert>
#include <cstring>
#include <cmath>
#include "validate.h"

using namespace std;

void check_case() {
    string line;
    /* Get test mode description from judge input file */
    assert(getline(judge_in, line));

    int value = -1;
    if (sscanf(line.c_str(), "fixed %d", &value) != 1) {
        if (sscanf(line.c_str(), "random %d", &value) == 1) {
            srandom(value);
            value = 1 + random() % 1000;
        } else if (sscanf(line.c_str(), "adaptive %d", &value) == 1) {
            srandom(value);
            value = -1;
        } else {
            assert(!"unknown input instructions");
        }
    }
    if (value == -1) {
        judge_message("I'm not committing to a value, will adaptively choose worst one\n");
    } else {
        judge_message("I'm thinking of %d\n", value);
    }

    int sol_lo = 1, sol_hi = 1000;
    int guesses = 0;
    for (int guesses = 0; guesses < 10; ++guesses) {
        int guess;
        if (!(author_out >> guess)) {
            wrong_answer("Guess %d: couldn't read an integer\n", guesses+1);
        }
        if (guess < 1 || guess > 1000) {
            wrong_answer("Guess %d is out of range: %d\n", guesses+1, guess);
        }
        judge_message("Guess %d is %d\n", guesses+1, guess);
        int diff;
        if (value == -1) {
            if (guess == sol_lo && sol_lo == sol_hi) {
                diff = 0;
            } else if (guess-1 - sol_lo > sol_hi - (guess+1)) {
                diff = -1;
            } else if (guess-1 - sol_lo < sol_hi - (guess+1)) {
                diff = 1;
            } else {
                diff = 2*(random() %2) - 1;
            }
        } else {
            diff = value - guess;
        }
        if (!diff) {
            cout << "correct\n";
            cout.flush();
            return;
        } else if (diff < 0) {
            cout << "lower\n";
            cout.flush();
            // Update the maximum possible hidden value.
            sol_hi = min(sol_hi, guess-1);
        } else {
            cout << "higher\n";
            cout.flush();
            // Update the minimum possible hidden value.
            sol_lo = max(sol_lo, guess+1);
        }
    }
    wrong_answer("Didn't get to correct answer in 10 guesses\n");

    return;
}

int main(int argc, char **argv) {
  init_io(argc, argv);

  check_case();

  /* Check for trailing output. */
  string trash;
  if (author_out >> trash) {
      wrong_answer("Trailing output\n");
  }

  /* Yay! */
  accept();
}
