#ifdef NDEBUG
#error Asserts must be enabled! Do not set NDEBUG.
#endif
#include <cstdlib>
#include <climits>
#include <cassert>
#include <vector>
#include <iostream>
#include <algorithm>
#include <sstream>
#include <fstream>
#include <string>
#include <map>
#include <set>
using namespace std;

// Implemented by you!
void run();

// PUBLIC API
// (extend if you need to)

[[noreturn]]
void die(const string& msg);
[[noreturn]]
void die_line(const string& msg);

struct ArgType {
	string _name, _x;
	ArgType(const string& name, const string& x) : _name(name), _x(x) {}
	operator string() const { return _x; }
	operator long long() const;
	operator bool() const;
	operator int() const;
};

struct IntType {
	long long _x;
	IntType(long long x) : _x(x) {}
	operator long long() const { return _x; }
	operator int() const;
	operator bool() const;
};

ArgType Arg(const string& name);

ArgType Arg(const string& name, long long _default);

string Arg(const string& name, const string& _default);

template <typename Vec>
void AssertUnique(const Vec& v);

namespace IO {
	IntType Int(long long lo, long long hi);
	double Float(double lo, double hi, bool strict = true);
	template<class T>
	vector<T> SpacedInts(long long count, T lo, T hi);
	vector<double> SpacedFloats(long long count, double lo, double hi);
	void Char(char expected);
	char Char();
	string Line();
	void Endl() { Char('\n'); }
	void Space() { Char(' '); }
	void Eof() { Char(-1); }
};
using namespace IO;

// INTERNALS

bool _validator_initialized;
struct _validator {
	map<string, string> params;
	set<string> used_params;

	void construct(int argc, char** argv) {
		_validator_initialized = true;
		for (int i = 1; i < argc; i++) {
			string s = argv[i];
			size_t ind = s.find('=');
			if (ind == string::npos) continue;
			auto before = s.substr(0, ind), after = s.substr(ind + 1);
			if (params.count(before))
				die("Duplicate parameter " + before);
			params[before] = after;
		}
	}

	void destroy() {
		assert(_validator_initialized);
		if (!params.empty()) {
			string name = params.begin()->first;
			die("Unused parameter " + name);
		}
		IO::Eof();
		_Exit(42);
	}

	bool has_var(const string& name) {
		if (!_validator_initialized) die("Must not read variables before main");
		return params.count(name) || used_params.count(name);
	}

	string get_var(const string& name) {
		if (!_validator_initialized) die("Must not read variables before main");
		if (used_params.count(name)) die("Must not read parameter " + name + " twice (either typo or slow)");
		if (!params.count(name)) die("No parameter " + name);
		string res = params.at(name);
		params.erase(name);
		used_params.insert(name);
		return res;
	}
} _validator_inst;

void die(const string& msg) {
	cerr << msg << endl;
	ofstream fout("/tmp/input_validator_msg", ios::app);
	fout << msg << endl;
	fout.close();
	_Exit(43);
}

ArgType::operator long long() const {
	string dummy;
	{
		long long num;
		istringstream iss(_x);
		iss >> num;
		if (iss && !(iss >> dummy)) return num;
	}
	{
		// We also allow scientific notation, for clarity
		long double num;
		istringstream iss(_x);
		iss >> num;
		if (iss && !(iss >> dummy)) return (long long)num;
	}
	die("Unable to parse value " + _x + " for parameter " + _name);
}

ArgType::operator int() const {
	long long val = (long long)*this;
	if (val < INT_MIN || val > INT_MAX)
		die("number " + to_string(val) + " is too large for an int for parameter " + _name);
	return (int)val;
}

ArgType::operator bool() const {
	long long val = (long long)*this;
	if (val < 0 || val > 1)
		die("number " + to_string(val) + " is not boolean (0/1), for parameter " + _name);
	return (bool)val;
}

IntType::operator int() const {
	long long val = (long long)*this;
	if (val < INT_MIN || val > INT_MAX)
		die_line("number " + to_string(val) + " is too large for an int");
	return (int)val;
}

IntType::operator bool() const {
	long long val = (long long)*this;
	if (val < 0 || val > 1)
		die_line("number " + to_string(val) + " is not boolean (0/1)");
	return (bool)val;
}

ArgType Arg(const string& name) {
	return {name, _validator_inst.get_var(name)};
}

ArgType Arg(const string& name, long long _default) {
	if (!_validator_inst.has_var(name))
		return {name, to_string(_default)};
	ArgType ret = Arg(name);
	(void)(long long)ret;
	return ret;
}

string Arg(const string& name, const string& _default) {
	if (!_validator_inst.has_var(name))
		return _default;
	return (string)Arg(name);
}

static int _lineno = 1, _consumed_lineno = -1, _hit_char_error = 0;
char _peek1();
void die_line(const string& msg) {
	if (!_hit_char_error && _peek1() == -1) die(msg);
	else if (_consumed_lineno == -1) die(msg + " (before reading any input)");
	else die(msg + " on line " + to_string(_consumed_lineno));
}

static char _buffer = -2; // -2 = none, -1 = eof, other = that char
char _peek1() {
	if (_buffer != -2) return _buffer;
	int val = getchar_unlocked();
	static_assert(EOF == -1, "");
	static_assert(CHAR_MIN == -128, "");
	if (val == -2 || val < CHAR_MIN || val >= CHAR_MAX) {
		_hit_char_error = 1;
		die_line("Unable to process byte " + to_string(val));
	}
	_buffer = (char)val;
	return _buffer;
}
void _use_peek(char ch) {
	_buffer = -2;
	if (ch == '\n') _lineno++;
	else _consumed_lineno = _lineno;
}
char _read1() {
	char ret = _peek1();
	_use_peek(ret);
	return ret;
}
string _token() {
	string ret;
	for (;;) {
		char ch = _peek1();
		if (ch == ' ' || ch == '\n' || ch == -1) {
			break;
		}
		_use_peek(ch);
		ret += ch;
	}
	return ret;
}
string _describe(char ch) {
	assert(ch != -2);
	if (ch == -1) return "EOF";
	if (ch == ' ') return "SPACE";
	if (ch == '\r') return "CARRIAGE RETURN";
	if (ch == '\n') return "NEWLINE";
	if (ch == '\t') return "TAB";
	if (ch == '\'') return "\"'\"";
	return string("'") + ch + "'";
}

IntType IO::Int(long long lo, long long hi) {
	string s = _token();
	if (s.empty()) die_line("Expected number, saw " + _describe(_peek1()));
	try {
		long long mul = 1;
		int ind = 0;
		if (s[0] == '-') {
			mul = -1;
			ind = 1;
		}
		if (ind == (int)s.size()) throw false;
		char ch = s[ind++];
		if (ch < '0' || ch > '9') throw false;
		if (ch == '0' && ind != (int)s.size()) throw false;
		long long ret = ch - '0';
		while (ind < (int)s.size()) {
			if (ret > LLONG_MAX / 10 - 20 || ret < LLONG_MIN / 10 + 20)
				throw false;
			ret *= 10;
			ch = s[ind++];
			if (ch < '0' || ch > '9') throw false;
			ret += ch - '0';
		}
		ret *= mul;
		if (ret < lo || ret > hi) die_line("Number " + s + " is out of range [" + to_string(lo) + ", " + to_string(hi) + "]");
		return {ret};
	} catch (bool) {
		die_line("Unable to parse \"" + s + "\" as integer");
	}
}

template<class T>
vector<T> IO::SpacedInts(long long count, T lo, T hi) {
	vector<T> res;
	res.reserve(count);
	for (int i = 0; i < count; i++) {
		if (i != 0) IO::Space();
		res.emplace_back((T)IO::Int(lo, hi));
	}
	IO::Endl();
	return res;
}

vector<double> IO::SpacedFloats(long long count, double lo, double hi) {
	vector<double> res;
	res.reserve(count);
	for (int i = 0; i < count; i++) {
		if (i != 0) IO::Space();
		res.emplace_back(IO::Float(lo, hi));
	}
	IO::Endl();
	return res;
}

double IO::Float(double lo, double hi, bool strict) {
	string s = _token();
	if (s.empty()) die_line("Expected floating point number, saw " + _describe(_peek1()));
	istringstream iss(s);
	double res;
	string dummy;
	iss >> res;
	if (!iss || iss >> dummy) die_line("Unable to parse " + s + " as a float");
	if (res < lo || res > hi) die_line("Floating-point number " + s + " is out of range [" + to_string(lo) + ", " + to_string(hi) + "]");
	if (res != res) die_line("Floating-point number " + s + " is NaN");
	if (strict) {
		if (s.find('.') != string::npos && s.back() == '0' && s.substr(s.size() - 2) != ".0")
			die_line("Number " + s + " has unnecessary trailing zeroes");
		if (s[0] == '0' && s.size() > 1 && s[1] == '0')
			die_line("Number " + s + " has unnecessary leading zeroes");
	}
	return res;
}

char IO::Char() {
	char ret = _read1();
	if (ret == -1) die_line("Expected character, saw EOF");
	return ret;
}

void IO::Char(char expected) {
	char ret = _peek1();
	if (ret != expected) die_line("Expected " + _describe(expected) + ", saw " + _describe(ret));
	_use_peek(ret);
}

string IO::Line() {
	string ret;
	for (;;) {
		char ch = IO::Char();
		if (ch == '\n') break;
		ret += ch;
	}
	return ret;
}

template <typename Vec>
void AssertUnique(const Vec& v_) {
	Vec v = v_;
	auto beg = v.begin(), end = v.end();
	sort(beg, end);
	int size = (int)(end - beg);
	for (int i = 0; i < size - 1; i++) {
		if (v[i] == v[i+1]) {
			ostringstream oss;
			oss << "Vector contains duplicate value " << v[i];
			die_line(oss.str());
		}
	}
}

int main(int argc, char** argv) {
	_validator_inst.construct(argc, argv);
	run();
	_validator_inst.destroy();
}

