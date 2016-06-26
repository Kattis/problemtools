/* Output validator for "A Different Problem".  This validator is only
 * provided as an example: the problem is so simple that it does not
 * need a custom output validator and it would be more appropriate to
 * use the default token-based diff validator.
 *
 * Note: if you start writing error messages in, say, Swedish, make
 * sure your file is UTF-8 coded.
 */
#include "validate.h"

using namespace std;
typedef long long int64;


bool read_input(istream &in) {
    // we don't need the input to check the output for this problem,
    // so we just discard it.
    int64 a, b;
    if (!(in >> a >> b))
        return false;
    return true;
}


int read_solution(istream &sol, feedback_function feedback) {
    // read a solution from "sol" (can be either judge answer or
    // submission output), check its feasibility etc and return some
    // representation of it

    int64 outval;
    if (!(sol >> outval)) {
        feedback("EOF or next token is not an integer");
    }
    return outval;
}

bool check_case() {
    if (!read_input(judge_in))
        return false;

    int64 ans = read_solution(judge_ans, judge_error);
    int64 out = read_solution(author_out, wrong_answer);

    if (ans != out) {
        wrong_answer("judge answer = %d but submission output = %d\n",
                     ans, out);
    }

    return true;
}


int main(int argc, char **argv) {
    init_io(argc, argv);

    while (check_case());

    /* Check for trailing output. */
    string trash;
    if (author_out >> trash) {
        wrong_answer("Trailing output");
    }

    accept();
}
