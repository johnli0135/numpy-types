from nptyping import *
import numpy as num

def f(p: bool, n: int) -> n + 2:
    if p:
        n = 1 + n
    else:
        pass
    return n + 1 if p else n + 2

a = 3
a = f(True, 3)
b = num.zeros(a)
c = num.zeros(f(True, f(False, 1))) + b
d = num.zeros((1, 2))
e = num.zeros((100, 100, 1000))

u = num.zeros(100)
v = num.zeros(100)
u = (u + v) * v
print(u)

u = u + 1
print(u)

g = num.ones(d.shape[0] + 1) + num.zeros(d.shape[1]) * 3 - 5
print(g)

A = num.zeros(3)
B = num.zeros(3)
C = num.zeros(3)
D = num.zeros(3)
E = num.zeros(3)
F = num.zeros(3)
G = num.zeros(3)
H = num.zeros(3)
I = num.zeros(3)
J = num.zeros(3)
K = num.zeros(3)
L = num.zeros(3)
M = num.zeros(3)
N = num.zeros(3)
O = num.zeros(3)
P = num.zeros(3)
Q = num.zeros(3)
R = num.zeros(3)
