from .general import SpecificationError
import re

class AlternativeMatch:
    def __init__(self, matchstr):
        raise NotImplementedError("Specialize in subclass")

    def check(self, val) -> bool:
        raise NotImplementedError("Specialize in subclass")

    @staticmethod
    def get_matcher(type, matchstr) -> "AlternativeMatch":
        matchers = {
            "string": StringMatch,
            "int": IntMatch,
            "float": FloatMatch,
            "bool": BoolMatch,
        }
        assert type in matchers
        return matchers[type](matchstr)


class StringMatch(AlternativeMatch):
    def __init__(self, matchstr):
        self.regex = re.compile(matchstr)

    def check(self, val) -> bool:
        return isinstance(val, str) and self.regex.match(val)

    def __str__(self) -> str:
        return self.regex.pattern



class IntMatch(AlternativeMatch):
    def __init__(self, matchstr: str | int):
        if isinstance(matchstr, int):
            self.start = self.end = matchstr
            return
        try:
            if matchstr.count(":") > 1:
                raise ValueError
            if ":" in matchstr:
                
                self.start, self.end = [
                    int(p) if p else None for p in map(str.strip, matchstr.split(":"))
                ]
            else:
                matchstr = matchstr.strip()
                if not matchstr:
                    raise SpecificationError("Match string for integer was left empty")
                self.start = self.end = int(matchstr)
        except ValueError:
            raise SpecificationError(
                f'Int match string should be of the form "A:B" where A and B can be parsed as ints or left empty, or a single integer, not "{matchstr}"'
            )

    def check(self, val) -> bool:
        if not isinstance(val, int):
            return False
        if self.start is not None:
            if val < self.start:
                return False
        if self.end is not None:
            if val > self.start:
                return False
        return True

    def __str__(self):
        A = str(self.start) if self.start is not None else ""
        B = str(self.end) if self.end is not None else ""
        if A == B and A != "":
            return str(A)
        return f"{A}:{B}"


class FloatMatch(AlternativeMatch):
    def __init__(self, matchstr: str):
        try:
            if matchstr.count(":") != 1:
                raise ValueError
            first, second = [p.strip() for p in matchstr.split(":")]
            self.start = float(first) if first else float("-inf")
            self.end = float(second) if second else float("inf")
        except ValueError:
            raise SpecificationError(
                'Float match string should be of the form "A:B" where A and B can be parsed as floats or left empty'
            )

    def check(self, val) -> bool:
        return isinstance(val, float) and self.start <= val <= self.end

    def __str__(self):
        A = str(self.start) if self.start != float("-inf") else ""
        B = str(self.end) if self.end != float("inf") else ""
        return f"{A}:{B}"


class BoolMatch(AlternativeMatch):
    def __init__(self, matchstr: str | bool):
        if isinstance(matchstr, bool):
            self.val = matchstr
            return
        matchstr = matchstr.strip().lower()
        if matchstr not in {"true", "false"}:
            raise SpecificationError(
                'Bool match string should be either "true" or "false"'
            )
        self.val = {"true": True, "false": False}[matchstr]

    def check(self, val) -> bool:
        return isinstance(val, bool) and val == self.val

    def __str__(self):
        return str(self.val)
