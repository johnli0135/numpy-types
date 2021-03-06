import util as U

# union-find with path compression
# items should form partial order under compare
# if items are not comparable, assume they are equivalent and add equality constraint
# chooses smallest representative for each component
class Substitution:
    def __init__(self, compare):
        self.m = {}
        self.compare = compare
        self.equalities = set()
        self.bias = True
        self.hash = None

    def __str__(self):
        constraints = ', '.join(str(l) + ' ~ ' + str(r) for l, r in self.equalities)
        return '{' + ', '.join(str(k) + ' -> ' + str(v) for k, v in self.m.items()) + '}' + \
            (' where ' + constraints if constraints != '' else '')

    def __hash__(self):
        if self.hash is None:
            self.hash = hash((
                tuple((a, self.find(a)) for a in self.m.items()),
                tuple(self.equalities)))
        return self.hash

    def __eq__(self, other):
        return (
            type(other) is Substitution and
            hash(self) == hash(other) and
            (self.m, self.equalities) == (other.m, other.equalities))

    def copy(self):
        σ = Substitution(self.compare)
        σ.m = dict(self.m)
        σ.equalities = set(self.equalities)
        σ.bias = self.bias
        σ.hash = self.hash
        return σ

    def find(self, a):
        traversed = []
        while a in self.m:
            traversed.append(a)
            a = self.m[a]
        for b in traversed:
            self.m[b] = a
        return a

    def union(self, a, b):
        self.bias = not self.bias
        a = self.find(a)
        b = self.find(b)
        if a == b:
            return self

        if self.compare(a, b):
            self.m[b] = a
        elif self.compare(b, a):
            self.m[a] = b
        else:
            self.m[[a, b][self.bias]] = [a, b][not self.bias]
            self.equalities |= {(a, b)}

        self.hash = None
        return self

    def gen(self, names):
        m = {}
        for k, v in self.m.items():
            m[k.gen(names)] = v.gen(names)
        self.m = m
        self.hash = None
        return self

    def extract_sets(self, predicate):
        from functools import reduce
        return set(reduce(U.union, 
            (predicate(l) | predicate(r)
                for l, r in self.equalities | set(self.m.items())),
            set()))

    def evars(self):
        return self.extract_sets(U.evars)

    def uvars(self):
        return self.extract_sets(U.uvars)

    def free_vars(self):
        return {a
            for l, r in self.equalities
            for a in l.vars() | r.vars()}

    # convert equality constraints to z3 formula
    # assumes items implement .to_z3, .evars, .uvars, .under
    # TODO: move this out of Substitution?
    def to_z3(self):
        import z3
        assumptions = {l.to_z3() == r.to_z3()
            for a in self.free_vars()
            for l, r in [(a, self.find(a))]
            if l != r}
        equalities = {l.to_z3() == r.to_z3()
            for left, right in self.equalities
            for l, r in [(left.under(self), right.under(self))]
            if l != r}
        return z3.And(list(equalities | assumptions))

if __name__ == '__main__':
    σ = Substitution(lambda a, b: a < b)
    σ.union(1, 2).union(3, 4).union(5, 6).union(7, 8) \
     .union(1, 3).union(5, 7) \
     .union(4, 8)
    print(σ)
