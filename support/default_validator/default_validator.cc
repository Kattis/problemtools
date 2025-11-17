#include <fstream>
#include <iostream>
#include <string>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cassert>
#include <cmath>
#include <cstdarg>

const int EXIT_AC = 42;
const int EXIT_WA = 43;

std::ifstream judgein, judgeans;
FILE *judgemessage = NULL;
FILE *diffpos = NULL;
int judgeans_pos = 0, stdin_pos = 0;
int judgeans_line = 1, stdin_line = 1;

// At some point we should rewrite this to something more C++. Now that we truncate long tokens, having this
// require c_str() calls gets even messier with object lifetimes.
void wrong_answer(const char *err, ...) {
	va_list pvar;
	va_start(pvar, err);
	fprintf(judgemessage, "Wrong answer on line %d of output (corresponding to line %d in answer file)\n", stdin_line, judgeans_line);
	vfprintf(judgemessage, err, pvar);
	fprintf(judgemessage, "\n");
	if (diffpos) {
		fprintf(diffpos, "%d %d", judgeans_pos, stdin_pos);
	}
	exit(EXIT_WA);
}

void judge_error(const char *err, ...) {
	va_list pvar;
	va_start(pvar, err);
	// If judgemessage hasn't been set up yet, write error to stderr
	if (!judgemessage) judgemessage = stderr;
	vfprintf(judgemessage, err, pvar);
	fprintf(judgemessage, "\n");
	assert(!"Judge Error");
}

bool isfloat(const char *s, double &val) {
	char trash[20];
	double v;
	if (sscanf(s, "%lf%10s", &v, trash) != 1) return false;
	val = v;
	return !std::isinf(v) && !std::isnan(v);
}

template <typename Stream>
void openfile(Stream &stream, const char *file, const char *whoami) {
	stream.open(file);
	if (stream.fail()) {
		judge_error("%s: failed to open %s\n", whoami, file);
	}
}

FILE *openfeedback(const char *feedbackdir, const char *feedback, const char *whoami) {
	std::string path = std::string(feedbackdir) + "/" + std::string(feedback);
	FILE *res = fopen(path.c_str(), "w");
	if (!res) {
		judge_error("%s: failed to open %s for writing", whoami, path.c_str());
	}
	return res;
}

/* Truncate string to avoid huge messages when teams forgot to print spaces.
 * If string is longer than limit (plus 5, as we don't want to replace just a
 * few characters with ...), we truncate and append "...". String may be in
 * arbitrary encoding, but as utf-8 is common, we make a small attempt to avoid
 * cutting in a utf-8 character. So output can be a few bytes longer than limit.
 */
std::string truncate(const std::string &str, size_t limit = 30) {
	if (str.length() <= limit + 5) {
		return str;
	}
	size_t cut = limit;
	// Heuristic to avoid cutting in the middle of a UTF-8 character.
	// A continuation byte in UTF-8 starts with binary 10.
	// We scan forwards from the limit to include the rest of a character,
	// but at most 3 extra bytes (for up to a 4-byte character).
	while (cut < str.length() && cut < limit + 4 && (str[cut] & 0xC0) == 0x80) {
		cut++;
	}
	return str.substr(0, cut) + "...";
}

/* Truncate a pair of strings (judge and user tokens). This preserves the first
 * few bytes of the common prefix, then adds ..., and then the first few bytes
 * starting from where the strings differ.
 */
std::pair<std::string, std::string> truncate_pair(const std::string &str1, const std::string &str2) {
	size_t diff_idx = 0;
	while (diff_idx < str1.length() && diff_idx < str2.length() && str1[diff_idx] == str2[diff_idx]) {
		diff_idx++;
	}

	std::string common_prefix = str1.substr(0, diff_idx);
	std::string s1 = str1.substr(diff_idx);
	std::string s2 = str2.substr(diff_idx);

	std::string p_part = truncate(common_prefix, 15);

	return std::make_pair(
		p_part + truncate(s1, 15),
		p_part + truncate(s2, 15)
	);
}

const char *USAGE = "Usage: %s judge_in judge_ans feedback_file [options] < user_out";

int main(int argc, char **argv) {
	if (argc < 4) {
		judge_error(USAGE, argv[0]);
	}
	judgemessage = openfeedback(argv[3], "judgemessage.txt", argv[0]);
	diffpos = openfeedback(argv[3], "diffposition.txt", argv[0]);
	openfile(judgein, argv[1], argv[0]);
	openfile(judgeans, argv[2], argv[0]);

	bool case_sensitive = false;
	bool space_change_sensitive = false;
	bool use_floats = false;
	double float_abs_tol = -1;
	double float_rel_tol = -1;

	for (int a = 4; a < argc; ++a) {
		if (!strcmp(argv[a], "case_sensitive")) {
			case_sensitive = true;
		} else if (!strcmp(argv[a], "space_change_sensitive")) {
			space_change_sensitive = true;
		} else if (!strcmp(argv[a], "float_absolute_tolerance")) {
			if (a+1 == argc || !isfloat(argv[a+1], float_abs_tol)) {
				judge_error(USAGE, argv[0]);
			}
			++a;
		} else if (!strcmp(argv[a], "float_relative_tolerance")) {
			if (a+1 == argc || !isfloat(argv[a+1], float_rel_tol)) {
				judge_error(USAGE, argv[0]);
			}
			++a;
		} else if (!strcmp(argv[a], "float_tolerance")) {
			if (a+1 == argc || !isfloat(argv[a+1], float_rel_tol)) {
				judge_error(USAGE, argv[0]);
			}
			float_abs_tol = float_rel_tol;
			++a;
		} else {
			judge_error(USAGE, argv[0]);
		}
	}
	use_floats = float_abs_tol >= 0 || float_rel_tol >= 0;

	std::string judge, team, judge_trunc, team_trunc;
	for (int token = 0; true; token++) {
		// Space!  Can't live with it, can't live without it...
		while (isspace(judgeans.peek())) {
			char c = (char)judgeans.get();
			if (space_change_sensitive) {
				int d = std::cin.get();
				if (c != d) {
					wrong_answer("Space change error: got %d expected %d", d, c);
				}
				if (d == '\n') ++stdin_line;
				++stdin_pos;
			}
			if (c == '\n') ++judgeans_line;
			++judgeans_pos;
		}
		while (isspace(std::cin.peek())) {
			char d = (char)std::cin.get();
			if (space_change_sensitive) {
				wrong_answer("Space change error: judge out of space, got %d from user", d);
			}
			if (d == '\n') ++stdin_line;
			++stdin_pos;
		}

		if (!(judgeans >> judge)) {
			break;
		}

		if (!(std::cin >> team)) {
			if (token == 0) {
				if (stdin_pos == 0) {
					judge_trunc = truncate(judge);
					wrong_answer(
						"User EOF while judge had more output; user output was empty.\n(Next judge token: %s)",
						judge_trunc.c_str()
					);
				} else {
					judge_trunc = truncate(judge);
					wrong_answer(
						"User EOF while judge had more output; user output contained only whitespace.\n(Next judge token: %s)",
						judge_trunc.c_str()
					);
				}
			} else {
				judge_trunc = truncate(judge);
				wrong_answer("User EOF while judge had more output\n(Next judge token: %s)", judge_trunc.c_str());
			}
		}

		double jval, tval;
		if (use_floats && isfloat(judge.c_str(), jval)) {
			if (!isfloat(team.c_str(), tval)) {
				team_trunc = truncate(team);
				wrong_answer("Expected float, got: %s", team_trunc.c_str());
			}
			if (!(fabs(jval - tval) <= float_abs_tol) &&
			   !(fabs(jval - tval) <= float_rel_tol * fabs(jval))) {
				// We don't want to truncate as a pair here, that just gets more confusing for floats (and something has
				// gone very wrong if we're dealing with floats so long we need to truncate anyway :)
				judge_trunc = truncate(judge);
				team_trunc = truncate(team);
				wrong_answer("Too large difference.\n Judge: %s\n User: %s\n Difference: %le\n (abs tol %le rel tol %le)", 
				             judge_trunc.c_str(), team_trunc.c_str(), jval-tval, float_abs_tol, float_rel_tol);
			}
		} else if (case_sensitive) {
			if (strcmp(judge.c_str(), team.c_str()) != 0) {
				std::tie(judge_trunc, team_trunc) = truncate_pair(judge, team);
				wrong_answer("String tokens mismatch\nJudge: \"%s\"\nUser: \"%s\"", judge_trunc.c_str(), team_trunc.c_str());
			}
		} else {
			if (strcasecmp(judge.c_str(), team.c_str()) != 0) {
				std::tie(judge_trunc, team_trunc) = truncate_pair(judge, team);
				wrong_answer("String tokens mismatch\nJudge: \"%s\"\nUser: \"%s\"", judge_trunc.c_str(), team_trunc.c_str());
			}
		}
		judgeans_pos += judge.length();
		stdin_pos += team.length();
	}

	if (std::cin >> team) {
		team_trunc = truncate(team);
		wrong_answer("Trailing output:\n%s", team_trunc.c_str());
	}

	exit(EXIT_AC);
}
