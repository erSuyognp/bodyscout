"""Competing self models. Each maps joint commands q (M x N) to fingertip x (M x 3).

ChainModel  : physics prior. A serial chain with unknown axes and offsets, fit by least squares.
GMMModel    : Kitchin style generative model of p(q, x). Forward = E[x|q], inverse = samples of q|x.
MLPModel    : black box neural network on sin/cos features.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from sklearn.mixture import GaussianMixture
from sklearn.neural_network import MLPRegressor

AX = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def _unit(theta, phi):
    return np.array([np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)])


def _rot(axis: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Rodrigues, vectorised over angles. axis (3,), q (M,) -> (M,3,3)."""
    x, y, z = axis
    K = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    s, c = np.sin(q)[:, None, None], np.cos(q)[:, None, None]
    return np.eye(3)[None] + s * K[None] + (1 - c) * (K @ K)[None]


class SelfModel:
    family = "base"

    def fit(self, Q, X, **kw):
        raise NotImplementedError

    def predict(self, Q) -> np.ndarray:
        raise NotImplementedError

    def rmse(self, Q, X) -> float:
        return float(np.sqrt(np.mean(np.sum((self.predict(Q) - X) ** 2, axis=1))))

    def describe(self) -> dict:
        return {"family": self.family}


def _tok(t):
    """Structure token: 'hz' = hinge about z, 'sx' = slide along x. A bare letter means a hinge."""
    return t if len(t) == 2 else "h" + t


class ChainModel(SelfModel):
    """Serial chain of hinge or slide joints. Per joint: an offset vector (3) and an axis vector (3).
    Hinge axes are normalised; a slide axis keeps its length, which absorbs the unknown metres per
    command unit. The structure (which joints hinge or slide) comes from hypotheses or random restarts."""

    family = "chain"

    def __init__(self, n: int, restarts: int = 6, seed: int = 0, any_types: bool = False):
        self.n = n
        self.restarts = restarts
        self.rng = np.random.default_rng(seed)
        self.any_types = any_types  # random restarts may guess slides too (body type unknown)
        self.params = None
        self.types = ["h"] * n

    def _unpack(self, p):
        offs = p[: 3 * self.n].reshape(self.n, 3)
        angs = p[3 * self.n: 6 * self.n].reshape(self.n, 3)
        tip = p[6 * self.n: 6 * self.n + 3]
        return offs, angs, tip

    def _fk(self, p, Q, types=None):
        types = types or self.types
        offs, angs, tip = self._unpack(p)
        M = Q.shape[0]
        pos = np.zeros((M, 3))
        R = np.broadcast_to(np.eye(3), (M, 3, 3)).copy()
        for i in range(self.n):
            pos = pos + R @ offs[i]
            if types[i] == "h":
                R = R @ _rot(angs[i] / (np.linalg.norm(angs[i]) + 1e-9), Q[:, i])
            else:
                pos = pos + np.einsum("mij,j->mi", R, angs[i]) * Q[:, i:i + 1]
        return pos + R @ tip

    def init_from_pattern(self, pattern, jitter=0.15, link_dir="z"):
        toks = [_tok(t) for t in pattern]
        offs = np.tile(np.array(AX[link_dir]) * 0.12, (self.n, 1)) + self.rng.normal(0, 0.03, (self.n, 3))
        offs[0] = [0.0, 0.0, 0.05]
        angs = np.array([np.array(AX[t[1]]) * (1.0 if t[0] == "h" else 0.06) for t in toks], float)
        angs += self.rng.normal(0, jitter, (self.n, 3)) * np.array([[1.0 if t[0] == "h" else 0.06] for t in toks])
        tip = np.array(AX[link_dir]) * 0.12
        return np.concatenate([offs.ravel(), angs.ravel(), tip]), [t[0] for t in toks]

    def _random_structure(self):
        types = self.rng.choice(["h", "s"], self.n) if self.any_types else ["h"] * self.n
        axes = ["z"] + list(self.rng.choice(["x", "y", "z"], self.n - 1))
        return [t + a for t, a in zip(types, axes)]

    def fit(self, Q, X, patterns=None, warm=None, weights=None):
        """patterns: structural hypotheses ('hz', 'sx', ...) from the hypothesizer.
        warm: (params, types) of a previous champion (transfer / damage recovery)."""
        Q, X = np.asarray(Q), np.asarray(X)
        w = np.ones(len(Q)) if weights is None else np.asarray(weights)
        sw = np.sqrt(w)[:, None]
        inits = []
        if warm is not None:
            wp, wt = warm if isinstance(warm, tuple) else (warm, ["h"] * self.n)
            if len(wt) == self.n:
                inits.append((np.asarray(wp, float), list(wt)))
        for pat in (patterns or []):
            if len(pat) == self.n:  # links might point up or sideways: try both
                inits.append(self.init_from_pattern(pat))
                inits.append(self.init_from_pattern(pat, link_dir="x"))
        while len(inits) < self.restarts:
            inits.append(self.init_from_pattern(self._random_structure(), jitter=0.4,
                                                link_dir=str(self.rng.choice(["z", "x"]))))
        best = None
        self.trials = []
        for p0, types in inits:
            res = lambda p, ty=types: ((self._fk(p, Q, ty) - X) * sw).ravel()  # noqa: E731
            r = least_squares(res, p0, method="lm" if 3 * len(Q) >= len(p0) else "trf", max_nfev=400)
            cost = float(np.sqrt(np.mean(r.fun ** 2) * 3))
            self.trials.append((cost, "".join(types)))
            if best is None or cost < best[0]:
                best = (cost, r.x, types)
        self.train_rmse, self.params, self.types = best[0], best[1], list(best[2])
        return self

    @property
    def warm_state(self):
        return (self.params.copy(), list(self.types))

    def predict(self, Q):
        return self._fk(self.params, np.atleast_2d(Q))

    def axes_letters(self):
        """Read back which axis each joint is closest to: an interpretable discovery."""
        _, angs, _ = self._unpack(self.params)
        return ["xyz"[int(np.argmax(np.abs(a)))] for a in angs]

    def tokens(self):
        return [t + a for t, a in zip(self.types, self.axes_letters())]

    def link_lengths(self):
        offs, _, tip = self._unpack(self.params)
        return [float(np.linalg.norm(o)) for o in offs[1:]] + [float(np.linalg.norm(tip))]

    def describe(self):
        return {"family": self.family, "axes": self.axes_letters(), "types": list(self.types),
                "structure": self.tokens(), "links_m": [round(v, 3) for v in self.link_lengths()]}


class GMMModel(SelfModel):
    """Joint density over [q, x] (Kitchin 2025). Supports conditional sampling of q given x."""

    family = "gmm"

    def __init__(self, n: int, seed: int = 0):
        self.n = n
        self.seed = seed
        self.gmm = None

    def fit(self, Q, X, **_):
        Z = np.hstack([Q, X * 10.0])  # scale x (metres) to radian-ish units
        best = None
        for k in (4, 8, 16, 24):
            if k * 4 > len(Z):
                break
            g = GaussianMixture(k, covariance_type="full", reg_covar=1e-5,
                                random_state=self.seed, max_iter=300).fit(Z)
            bic = g.bic(Z)
            if best is None or bic < best[0]:
                best = (bic, g)
        self.gmm = best[1]
        return self

    def _condition(self, given, idx_g, idx_t):
        g = self.gmm
        means, covs, w = g.means_, g.covariances_, g.weights_
        cm, cc, logp = [], [], []
        for k in range(len(w)):
            mg, mt = means[k][idx_g], means[k][idx_t]
            Sgg = covs[k][np.ix_(idx_g, idx_g)]
            Stg = covs[k][np.ix_(idx_t, idx_g)]
            Stt = covs[k][np.ix_(idx_t, idx_t)]
            inv = np.linalg.inv(Sgg)
            d = given - mg
            cm.append(mt + d @ (Stg @ inv).T)
            cc.append(Stt - Stg @ inv @ Stg.T)
            _, logdet = np.linalg.slogdet(Sgg)
            maha = np.einsum("ij,jk,ik->i", d, inv, d)
            logp.append(np.log(w[k]) - 0.5 * (logdet + maha))
        logp = np.array(logp).T  # (M, K)
        resp = np.exp(logp - logp.max(1, keepdims=True))
        resp /= resp.sum(1, keepdims=True)
        return np.array(cm).transpose(1, 0, 2), np.array(cc), resp

    def predict(self, Q):
        Q = np.atleast_2d(Q)
        n = self.n
        cm, _, resp = self._condition(Q, list(range(n)), list(range(n, n + 3)))
        return np.einsum("mk,mkd->md", resp, cm) / 10.0

    def sample_inverse(self, x, n_samples=32, rng=None):
        """Many joint configurations that could reach x: the redundant IK answer."""
        rng = rng or np.random.default_rng(self.seed)
        n = self.n
        cm, cc, resp = self._condition(np.atleast_2d(x) * 10.0, list(range(n, n + 3)), list(range(n)))
        ks = rng.choice(len(resp[0]), size=n_samples, p=resp[0])
        return np.array([rng.multivariate_normal(cm[0, k], cc[k]) for k in ks])

    def density(self, Q, X):
        return self.gmm.score_samples(np.hstack([Q, X * 10.0]))


class MLPModel(SelfModel):
    family = "mlp"

    def __init__(self, n: int, seed: int = 0):
        self.n = n
        self.net = MLPRegressor(hidden_layer_sizes=(64, 64), activation="tanh", max_iter=3000,
                                learning_rate_init=3e-3, random_state=seed)

    @staticmethod
    def _f(Q):
        Q = np.atleast_2d(Q)
        return np.hstack([np.sin(Q), np.cos(Q)])

    def fit(self, Q, X, **_):
        self.net.fit(self._f(Q), np.asarray(X) * 10.0)
        return self

    def predict(self, Q):
        return self.net.predict(self._f(Q)) / 10.0


FAMILIES = {"chain": ChainModel, "gmm": GMMModel, "mlp": MLPModel}
