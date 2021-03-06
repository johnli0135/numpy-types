import util as U
import pattern as P
import context as C
import ast as A
import nptype as T
from callbacks import callbacks

typerule = callbacks

# typechecking rule
# pattern : str or AST pattern
# action : Checker * Context * ..kwargs -> [Context * ?a]
# names of arguments should match names of capture groups in pattern
class Rule:
    def __init__(self, pattern, action, name=None):
        self.s = pattern if type(pattern) is str else None
        self.pattern = P.make_pattern(pattern) if type(pattern) is str else pattern
        self.action = action
        self.name = name

    def __str__(self):
        if self.s is not None:
            return '{} ({})'.format(self.s, self.name)
        else:
            return '{} ({})'.format(P.pretty(P.explode(self.pattern)), self.name)

# checker failed at some ast node
class ASTError(Exception):
    def __init__(self, ast):
        self.ast = ast

# type-checking failed
class CheckError(ASTError):
    def __init__(self, ast, errors):
        self.ast = ast
        self.errors = errors # rules attempted and errors they produced

    def __str__(self):
        return '{}\nfor:\n{}'.format(
            P.pretty(P.explode(self.ast)),
            '\n'.join('{}\n{}'.format(
                r.name,
                U.indent('  ', str(e))) for r, e in self.errors))

    # pretty-print the error, where s is the source code that was being analyzed
    def pretty(self, s):
        def error_paths(self):
            if type(self) is not CheckError:
                return [[self]]
            paths = []
            for _, e in self.errors:
                paths.extend([[self] + p for p in error_paths(e)])
            return paths

        paths = error_paths(self)

        def pretty(e):
            if type(e[-1]) is ConfusionError:
                return e[-1].pretty(s)
            return '{}\n{}'.format(U.highlight(e[-2].ast, s), str(e[-1]))

        if len(paths) == 1:
            return pretty(paths[0])

        value_errors = [p for p in paths
            if type(p[-1]) is ValueError and 'Unbound identifier' not in str(p[-1])]
        unbound_idents = [p for p in paths
            if type(p[-1]) is ValueError and 'Unbound identifier' in str(p[-1])]
        unif_errors = [p for p in paths if type(p[-1]) is T.UnificationError]
        grouped_unif_errors = {}
        for reason in {p[-1].reason for p in unif_errors}:
            grouped_unif_errors[reason] = [p for p in unif_errors if p[-1].reason == reason]
        confusion_errors = [p for p in paths if type(p[-1]) is ConfusionError]

        summary = ''
        if len(value_errors) > 0:
            summary = '{} value errors'.format(len(value_errors))
        if len(unbound_idents) > 0:
            summary += '\n{} unbound identifier errors'.format(len(unbound_idents))
        if len(grouped_unif_errors.items()) > 0:
            for reason, subpaths in sorted(grouped_unif_errors.items(), key=lambda a: -len(a[1])):
                summary += '\n{} unification errors ({})'.format(len(subpaths), reason)
        if len(confusion_errors) > 0:
            summary += '\n{} confusion errors'.format(len(confusion_errors))

        if len(value_errors) > 0:
            header = '' if summary == '' else 'Among\n' + U.indent('  ', summary)
            return header + ''.join('\n' + pretty(e) for e in value_errors)
        if len(confusion_errors) > 0:
            header = '' if summary == '' else 'Among\n' + U.indent('  ', summary)
            return header + ''.join('\n' + pretty(e) for e in confusion_errors)

        coords = {U.coords(p[-2].ast) for p in paths}
        footer = summary if len(paths) > 10 else ''.join({'\n' + str(p[-1]) for p in paths})
        return '{}{}'.format(
            '\n'.join(
                U.code_pointers(row, [c for r, c in coords if r == row], s)
                for row in {r for r, _ in coords}),
            footer)

# no suitable pattern
class ConfusionError(ASTError):
    def __init__(self, ast):
        self.ast = ast
    def pretty(self, s):
        return '{}\nNo applicable rule'.format(U.highlight(self.ast, s))

no_op = lambda s, a: [(s, a)]

# type-checker acting on a set of checking rules
class Checker:
    def __init__(self, rules, return_type=T.TNone(), careful=False, _ast_memo={}, _memo={}):
        self.rules = rules
        self.return_type = return_type
        self.careful = careful
        # memoize past queries (remember which rules worked & the results they yielded)
        self._ast_memo = _ast_memo
        self._memo = _memo

    def carefully(self):
        return Checker(
            self.rules,
            return_type = self.return_type,
            careful = True,
            _ast_memo = self._ast_memo,
            _memo = self._memo)

    def returning(self, r):
        return Checker(
            self.rules,
            return_type = r,
            careful = self.careful,
            _ast_memo = self._ast_memo,
            _memo = self._memo)

    # try each of the rules in order and run action corresponding to first matching rule
    # Checker * [Context] * AST * (Context * a -> [Context * b]) -> [Context * b]
    # fail with ConfusionError if no rules match
    # fail with CheckError if all rules that matched threw
    def analyze(self, Γs, ast, f = no_op):
        k_ast = P.simplify(ast)
        k = (ast, tuple(Γs))
        possible_errors = (ValueError, CheckError, ConfusionError, T.UnificationError)

        # compute results for each applicable pattern
        hits, a = self._memo[k] if k in self._memo else (0, None)
        options = []
        if isinstance(a, Exception):
            raise a
        if a is not None:
            options = a
            self._memo[k] = (hits + 1, options)
        else:
            if k_ast in self._ast_memo:
                ast_hits, matches = self._ast_memo[k_ast]
            else:
                ast_hits = 0
                matches = [(rule, a)
                    for rule in self.rules
                    for a in [P.matches(rule.pattern, ast)]
                    if a is not None]
            self._ast_memo[k_ast] = (ast_hits + 1, matches)

            options = []
            for Γ in Γs:
                errors = []
                for rule, match in matches:
                    try:
                        options.append((rule, rule.action(self, Γ.copy(), **match)))
                    except possible_errors as e:
                        errors.append((rule, e))
                if options == []:
                    e = ConfusionError(ast) if errors == [] else CheckError(ast, errors)
                    self._memo[k] = (1, e)
                    raise e
            self._memo[k] = (1, options)

        # run continuation with each result
        errors = []
        for rule, option in options:
            try:
                return [b for s, a in option for b in f(s, a)]
            except possible_errors as e:
                errors.append((rule, e))
        raise ConfusionError(ast) if errors == [] else CheckError(ast, errors)

    def check(self, ast):
        try:
            pairs = self.analyze([C.Context()], ast)
            state = C.State([s for s, _ in pairs])
            return U.verify(state)
        except (ValueError, CheckError, T.UnificationError) as e:
            if not self.careful and 'Unsatisfiable constraint' in str(e):
                self.carefully().check(ast)
            else:
                raise

    def dump_memo(self, s):
        for ast, (hits, rules) in sorted(self._ast_memo.items(), key=lambda a: a[1][0]):
            print('{}\n{} hits ({} rules)'.format(ast, hits, len(rules)))
        for (ast, Γs), (hits, _) in sorted(self._memo.items(), key=lambda a: a[1][0]):
            print('{}\n{} hits ({})'.format(U.highlight(ast, s), hits, type(ast).__name__))
            print('Contexts:')
            for c in Γs:
                print(str(c.reduced()))

# -------------------- rule/checker combinators --------------------

# given a pattern string s, and assumptions about the types of each capture group,
# return return_type
def expression(s, assumptions, return_type, name=None):
    to_type = lambda a: (T.parse(a) if type(a) is str else a)
    assumptions = dict((k, to_type(v)) for k, v in assumptions.items())
    return_type = to_type(return_type)

    @typerule({**globals(), **locals()})
    def f(self, Γ, **kwargs):
        names = {v for _, t in assumptions.items() for v in t.names()} | return_type.names()

        for name, ast in analyzed, Γ <- kwargs.items():
            Γ, inferred_type <- self.analyze([Γ], ast)
            yield name, inferred_type

        renaming = dict(zip(names, U.fresh_ids))
        instantiate = lambda t: t.renamed(renaming).eapp()
        for name, inferred_type in analyzed:
            Γ.unify(inferred_type, instantiate(assumptions[name]))
        return [(Γ, instantiate(return_type))]

    return Rule(s, f, name)

def literal(s, t, name=None):
    return Rule(s, lambda _, Γ: [(Γ, t)], name)

# binary infix operator op and corresponding variable type v and type constructor f
def binary_operator(op, v, f, name=None):
    return expression(
        '_a {} _b'.format(op), 
        {'a': v(T.parse('a')), 'b': v(T.parse('b'))},
        f(v(T.parse('a')), v(T.parse('b'))),
        name)

# extend an environment
def extend(self, Γ, bindings, k=no_op):
    c = Γ.copy()
    for a, t in bindings.items():
        t = T.parse(t)
        c.annotate(a, t)
    return k(c, None)

# -------------------- basic type-checking rules --------------------

@typerule(globals())
def analyze_body(self, Γ, body, k=no_op): 
    for a in __, Γ <- body: 
        Γ, _ <- self.analyze([Γ], a)
        if self.careful: 
            U.verify(Γ)
    return k(Γ, None)

module = Rule(P.raw_pattern('__body'), analyze_body, 'module')

@typerule(globals())
def analyze_cond(self, Γ, p, top, bot, k=no_op):
    Γ, t <- self.analyze([Γ], p)
    top_Γ = Γ.copy().assume(t)
    bot_Γ = Γ.copy().assume(T.Not(t))
    top_results = analyze_body(self, top_Γ, top)
    bot_results = analyze_body(self, bot_Γ, bot)
    return [b
        for s, a in top_results + bot_results
        for b in k(s, a)]

cond = Rule('''
if _p:
    __top
else:
    __bot
''', analyze_cond, 'cond')

skip = Rule('pass', lambda self, Γ: [(Γ, None)], 'skip')

@typerule(globals())
def analyze_cond_expr(self, Γ, p, l, r, k=no_op):
    Γ, t <- self.analyze([Γ], p)
    top_Γ = Γ.copy().assume(t)
    bot_Γ = Γ.copy().assume(T.Not(t))
    top_results = self.analyze([top_Γ], l)
    bot_results = self.analyze([bot_Γ], r)
    return [b
        for s, a in top_results + bot_results
        for b in k(s, a)]

cond_expr = Rule('_l if _p else _r', analyze_cond_expr, 'cond_expr')

@typerule(globals())
def analyze_assign(self, Γ, lhs, rhs, anno=None):
    assert type(lhs) is A.Name
    lhs = U.ident2str(lhs)

    if rhs is None and anno is not None:
        return [(Γ.annotate(lhs, T.from_ast(anno), fixed=True), None)]

    Γ, new_t <- self.analyze([Γ], rhs)

    if lhs in Γ:
        old_t = Γ.typeof(lhs)
        new_t = new_t.under(Γ)
        if not (isinstance(old_t, T.AExp) and isinstance(new_t, T.AExp) or
                isinstance(old_t, T.BExp) and isinstance(new_t, T.BExp)):
            Γ.unify(old_t, new_t)
    if anno is not None:
        t = T.from_ast(anno)
        Γ.unify(new_t, t)
        Γ.annotate(lhs, t, fixed=True)
    else:
        new_t = new_t.under(Γ)
        if type(new_t) is T.Fun:
            # uninstantiate function bindings
            new_t = new_t.flipped(Γ.fixed)
        Γ.annotate(lhs, new_t)
    return [(Γ, None)]

assign_anno = Rule(P.raw_pattern('_lhs: _anno = _rhs').body[0],
    analyze_assign, 'assign_anno')

assign = Rule('_lhs = _rhs', analyze_assign, 'assign')

def analyze_ident(self, Γ, a):
    t = Γ.typeof(U.ident2str(a))
    if type(t) is T.Fun:
        # immediately instantiate fn bindings (prenex poly)
        t = Γ.instantiate(t)
    return [(Γ, t)]

ident = Rule('a__Name', analyze_ident, 'ident')
attr_ident = Rule('a__Attribute', analyze_ident, 'attr_ident')

@typerule(globals())
def analyze_fun_def(self, Γ, f, args, return_type, body):
    arg_types = []
    nested_Γ = Γ.copy()
    for arg in args:
        a, t = T.from_ast(arg)
        nested_Γ.annotate(a, t, fixed=True)
        arg_types.append(t)
    r = T.from_ast(return_type)
    arg_types = T.Tuple(arg_types) if len(arg_types) != 1 else arg_types[0]
    fun_type = T.Fun(arg_types, r)
    nested_Γ.annotate(f, fun_type, fixed=True)

    polymorphic_fun_type = fun_type.fresh(Γ.fixed)
    #print('fun_type =', fun_type)
    #print('polymorphic_fun_type =', polymorphic_fun_type)

    Γ1, _ <- analyze_body(self.returning(r), nested_Γ, body)
    U.verify(Γ1)
    return [(Γ.annotate(f, polymorphic_fun_type), None)]

fun_def = Rule('def _f(__args) -> _return_type:\n    __body', analyze_fun_def, 'fun_def')

lit_None = literal('None', T.TNone())
lit_True = literal('True', T.BLit(True))
lit_False = literal('False', T.BLit(False))

bool_or = binary_operator('or', T.BVar, T.Or, 'bool_or')
bool_and = binary_operator('and', T.BVar, T.And, 'bool_and')
bool_not = expression('not _a', {'a': 'bool(a)'}, 'not bool(a)', 'bool_not')

lit_num = Rule('num__Num', lambda _, Γ, num:
    [(Γ, T.ALit(int(num.n)))], 'lit_num')
int_add = binary_operator('+', T.AVar, T.Add, 'int_add')
int_mul = binary_operator('*', T.AVar, T.Mul, 'int_mul')

int_eq = binary_operator('==', T.AVar, T.Eq, 'int_eq')
int_lt = binary_operator('<', T.AVar, T.Lt, 'int_lt')
int_gt = binary_operator('>', T.AVar, T.Gt, 'int_gt')
int_le = binary_operator('<=', T.AVar, T.Le, 'int_le')
int_ge = binary_operator('>=', T.AVar, T.Ge, 'int_ge')

asrt = Rule('assert _a', lambda self, Γ, a:
    self.analyze([Γ], a, lambda Γ, e: [(Γ.assume(e), None)]))

ret = Rule('return _a', lambda self, Γ, a:
    self.analyze([Γ], a, lambda Γ, t:
        [(Γ.unify(self.return_type, t), None)]), 'return')

@typerule(globals())
def analyze_fun_call(self, Γ, f, args):
    for arg in arg_types, Γ <- args:
        Γ, inferred_type <- self.analyze([Γ], arg)
        yield inferred_type
    arg_type = T.Tuple(arg_types)
    Γ, t <- self.analyze([Γ], f)
    a = next(U.fresh_ids)
    b = next(U.fresh_ids)
    Γ.fix({a, b})
    fn = T.Fun(T.EVar(a), T.EVar(b))
    Γ.unify(t, fn)
    #print(t, '~', fn)
    #print(arg_type.under(Γ), '~', fn.a.under(Γ))
    Γ.unify(arg_type, fn.a)
    #print(
    #    '=>', fn.b, '=', fn.b.under(Γ),
    #    'after applying', P.pretty(P.explode(f)))
    #print('Γ =', Γ)
    return [(Γ, fn.b)]

fun_call = Rule('_f(__args)', analyze_fun_call, 'fun_call')

print_expr = expression('print(_a)', {'a': T.UVar('a')}, T.TNone(), 'print_expr')
print_stmt = Rule(
    P.raw_pattern('print(_a)').body[0],
    lambda self, Γ, a: self.analyze([Γ], a, lambda Γ, _: [(Γ, None)]))

@typerule(globals())
def analyze_lambda_expr(self, Γ, args, e):
    arg_ids = tuple(U.take(len(args), U.fresh_ids))
    arg_types = [T.EVar(name) for name in arg_ids]
    Γ1 = Γ.copy()
    for a, t in zip(map(U.ident2str, args), arg_types):
        Γ1.annotate(a, t, fixed=True)
    Γ2, t <- self.analyze([Γ1], e)
    #print('Γ2 =', Γ2)
    #print('t =', t, '=>', t.under(Γ2))
    #print('args =', ', '.join(map(str, arg_types)))
    fn = T.Fun(T.Tuple(arg_types), t).under(Γ2)
    #print('Γ =', Γ)
    for name in Γ.Γ:
        t_Γ = Γ.typeof(name)
        t_Γ2 = t_Γ.under(Γ2)
        Γ.unify(t_Γ, t_Γ2)
        Γ.fix(t_Γ2.names() & (Γ2.fixed - Γ1.fixed))
    #print('new Γ =', Γ)
    #print('returning', fn)
    #print()
    return [(Γ, fn)]

lambda_expr = Rule('lambda __args: _e', analyze_lambda_expr, 'lambda_expr')

# -------------------- basic rule set --------------------

basic_rules = [
    module,
    assign_anno,
    assign,
    skip,
    ident,
    attr_ident,
    lit_None, lit_True, lit_False, lit_num,
    bool_or, bool_and, bool_not, int_add, int_mul,
    int_eq, int_lt, int_gt, int_le, int_ge,
    cond, cond_expr,
    fun_def,
    fun_call,
    lambda_expr,
    asrt,
    ret,
    print_expr,
    print_stmt]

if __name__ == '__main__':
    arr_zeros = expression('np.zeros(_a)', {'a': 'int(a)'}, 'array[int(a)]', 'arr_zeros')
    add_row = expression('add_row(_a)', {'a': 'array[int(a)]'}, 'array[int(a) + 1]', 'add_row')
    smush = expression(
        'smush(_a, _b)',
        {'a': 'array[int(a)]', 'b': 'array[int(a)]'},
        'array[int(a)]', 'smush')
    import_numpy = Rule('import numpy as np',
        lambda self, Γ: extend(self, Γ, {
            'np.ones': 'Fun((int(a),), array[a])'}),
        'import_numpy')

    def try_check(s):
        rules = basic_rules + [arr_zeros, add_row, smush, import_numpy]
        c = Checker(rules, return_type=T.parse('array[3]'))
        c.careful = False
        try:
            state = c.check(A.parse(s))
            print('OK')
            return state
        except (ValueError, ConfusionError, CheckError) as e:
            if type(e) in (CheckError, ConfusionError):
                print(e.pretty(s))
            else:
                print(e)
        finally:
            print()

    try_check('''
a = True
a = None
''')

    try_check('''
d = add_row(np.zeros(3))
e = add_row(d)
f = smush(d, e)
''')

    try_check('''
a = True or False
a = not False
b = (1 + 1) * (1 + 1 + 1)
c = np.zeros(3)
''')

    try_check('''
a = add_row(np.zeros(2))
return a
b = np.zeros(3)
return b
c = np.zeros(1 + 1 + 1)
return c
''')

    try_check('''
n = 1
m = 1
if False:
    n = n + 1
else:
    m = m + 1
a = np.zeros(n + m)
b = smush(a, np.zeros(3))
''')

    try_check('''
def f(p: bool, a: int, b: array[a]) -> array[a + 1]:
    if p:
        return np.zeros(1 + a)
    else:
        return smush(add_row(b), np.zeros(a + 2))
''')

    try_check('''
def f(p : bool, n : int) -> array[n + 2]:
    if p:
        n = 1 + n
        r = np.zeros(n)
    else:
        r = np.zeros(n + 1)
    return smush(add_row(r), np.zeros(n + 1 if p else n + 2))
''')

    try_check('''
def succ(a : int) -> int:
    return a + 1
n = 3
a = np.zeros(succ(n))
''')

    try_check('''
a += 1
''')

    try_check('''
import numpy as np
a = np.ones(3)
b = np.zeros(4)
c = smush(a, b)
''')

    try_check('''
import numpy as np
a = np.ones(3)
b = np.zeros(3)
c = smush(a, b)
''')

    try_check('''
b: bool
b = None
''')

    try_check('b: bool = None')

    try_check('b: bool = (True or False) and True')

    print(try_check('''
b = np.zeros(3)
f = lambda a: add_row(smush(a, b))
compose = lambda f, g: lambda x: f(g(x))
flip = lambda f: lambda a: lambda b: f(b)(a)
'''))
