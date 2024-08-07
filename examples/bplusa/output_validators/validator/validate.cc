#include "validate.h"

#include <bits/stdc++.h>
using namespace std;

#define rep(i, a, b) for(int i = a; i < (b); ++i)
#define all(x) begin(x), end(x)
#define sz(x) (int)(x).size()
typedef long long ll;
typedef pair<int, int> pii;
typedef vector<int> vi;
typedef vector<vi> vvi;
typedef long double ld;

#define repe(i, container) for (auto& i : container)

void check_isvalid(int a, int b, int c, feedback_function feedback)
{
	if (a==b) feedback("a is equal to b");
	if (a+b!=c) feedback("b+a!=c");
}

const int HUNDRED_THOUSAND = int(1e5);
int main(int argc, char **argv) {
	init_io(argc, argv);

	// Read the testcase input
	int c;
	judge_in >> c;

	auto check = [&](istream& sol, feedback_function feedback) {
		int a, b;
		// Don't get stuck waiting for output from solution
		if(!(sol >> a >> b)) feedback("Expected more output");
		// Validate constraints
		if (a < -HUNDRED_THOUSAND || a > HUNDRED_THOUSAND) feedback("a is too big or large");
		if (b < -HUNDRED_THOUSAND || b > HUNDRED_THOUSAND) feedback("b is too big or large");

		// Check that they actually solved the task
		check_isvalid(a, b, c, feedback);

		// Disallow trailing output
		string trailing;
		if(sol >> trailing) feedback("Trailing output");
		return true;
	};

	// Check both the judge's and contestants' output
	// It is good practice to not assume that the judge is correct/optimal
	bool judge_found_sol = check(judge_ans, judge_error);
	bool author_found_sol = check(author_out, wrong_answer);

	// In this problem, having a return value from check is unnecessary
	// However, if there isn't always a solution, we will get a nice
	// judge error if the judge solution claims no solution exists, while
	// a contestant finds one
	if(!judge_found_sol)
		judge_error("NO! Judge did not find valid solution");

	if(!author_found_sol)
		wrong_answer("Contestant did not find valid solution");

	accept();
}
