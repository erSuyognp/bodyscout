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
        err = self.predict(Q) - np.asarray(X)
        # one marker: sum over xyz. several fingertips: sum over xyz, then average tips too.
        axis = 1 if err.ndim == 2 else -1
        return float(np.sqrt(np.mean(np.sum(err ** 2, axis=axis))))

    def describe(self) -> dict:
        return {"family": self.family}


def _tok(t):
    """Structure token: 'hz' = hinge about z, 'sx' = slide along x. A bare letter means a hinge."""
    return t if len(t) == 2 else "h" + t


class ChainModel(SelfModel):
    """Serial chain of hinge or slide joints, or a tree when several fingertips are observed.

    Per joint: an offset vector (3) and an axis vector (3). Hinge axes are normalised; a slide axis
    keeps its length, which absorbs the unknown metres per command unit. The structure (which joints
    hinge or slide) comes from hypotheses or random restarts. With several fingertips, `limbs` names
    each tip's channels from the shared trunk outward and predict() returns one point per tip.
    One fingertip keeps the serial chain."""

    family = "chain"
    NULL_RTOL = 1e-6      # singular values below this fraction of the largest span the null space
    SAME_TIPS = 1e-6      # metres; the shortest equivalent body must reproduce every training tip
    NULL_SHARE = 0.25     # a link is suspect when this much of its length direction lies in it
    PROBE_DL = 0.05       # metres of length change used to probe each link
    TIP_TOL = 5e-4        # metres; a length change that moves no training tip this far is invisible

    def __init__(self, n: int, restarts: int = 6, seed: int = 0, any_types: bool = False):
        self.n = n
        self.restarts = restarts
        self.rng = np.random.default_rng(seed)
        self.any_types = any_types  # random restarts may guess slides too (body type unknown)
        self.params = None
        self.report_params = None  # same tips as params, shortest links; for describe() only
        self.types = ["h"] * n   # chain order
        self.identifiable = None
        self.order = list(range(n))  # chain position i is driven by channel order[i]
        self.tree = False            # True once fit on several fingertips: a trunk plus one chain per tip

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

    def fit(self, Q, X, patterns=None, warm=None, weights=None, order=None, limbs=None):
        """patterns: structural hypotheses ('hz', 'sx', ...) from the hypothesizer, one per channel.
        warm: (params, types[, order]) of a previous champion (transfer / damage recovery).
        order: which channel drives each link, base first (channels need not be wired in chain order).
        limbs: for several fingertips, each tip's channels from the trunk out. None keeps the serial chain.
        Parameters, types and links are kept in chain order; tokens() reports in channel order."""
        if np.asarray(X).ndim == 3:
            return self._fit_tree(Q, X, patterns, warm, weights, limbs)
        self.tree = False
        self.order = list(order) if order is not None else list(range(self.n))
        Q, X = np.asarray(Q)[:, self.order], np.asarray(X)
        w = np.ones(len(Q)) if weights is None else np.asarray(weights)
        sw = np.sqrt(w)[:, None]
        inits = []
        if warm is not None:
            wp, wt, wo = (tuple(warm) + (list(range(self.n)),))[:3] if isinstance(warm, tuple)                 else (warm, ["h"] * self.n, list(range(self.n)))
            if len(wt) == self.n and list(wo) == self.order:
                inits.append((np.asarray(wp, float), list(wt)))
        for pat in (patterns or []):
            if len(pat) == self.n:  # links might point up or sideways: try both
                pat = [pat[c] for c in self.order]
                inits.append(self.init_from_pattern(pat))
                inits.append(self.init_from_pattern(pat, link_dir="x"))
        while len(inits) < self.restarts:
            inits.append(self.init_from_pattern(self._random_structure(), jitter=0.4,
                                                link_dir=str(self.rng.choice(["z", "x"]))))
        best = None
        self.trials = []
        for p0, types in inits:
            res = lambda p, ty=types: ((self._fk(p, Q, ty) - X) * sw).ravel()  # noqa: E731
            # trf, not lm: scipy's MINPACK lm gives different answers for identical inputs depending on
            # where its work buffers land in memory, which breaks run to run reproducibility
            r = least_squares(res, p0, method="trf", max_nfev=400)
            cost = float(np.sqrt(np.mean(r.fun ** 2) * 3))
            self.trials.append((cost, "".join(types)))
            if best is None or cost < best[0]:
                best = (cost, r.x, types)
        self.train_rmse, self.params, self.types = best[0], best[1], list(best[2])
        # predict and warm start from the raw fit; report links from its shortest equivalent body,
        # so reporting never changes what the swarm does
        self.report_params = self._shortest_equivalent(self.params, Q, self._jacobian(self.params, Q))
        J = self._jacobian(self.report_params, Q)
        self.identifiable = self._identifiability(Q, J, self._null_basis(J))
        return self

    def _jacobian(self, p, Q):
        """Data Jacobian of the training tips, by central differences."""
        h = 1e-6
        J = np.empty((3 * len(Q), p.size))
        for k in range(p.size):
            d = np.zeros_like(p)
            d[k] = h
            J[:, k] = (self._fk(p + d, Q, self.types) - self._fk(p - d, Q, self.types)).ravel() / (2 * h)
        return J

    def _null_basis(self, J):
        """Columns spanning the directions the data cannot see (singular value < NULL_RTOL * max)."""
        _, s, vt = np.linalg.svd(J, full_matrices=True)
        s_all = np.zeros(J.shape[1])
        s_all[: len(s)] = s
        return vt[s_all < self.NULL_RTOL * s.max()].T

    def _shortest_equivalent(self, p, Q, J):
        """Same tips, shortest links. Height between parallel hinges (SCARA, the base under a yaw
        joint) can sit in any link, so raw fits wander to metre long links. Those trades are exact
        linear moves of the offsets, so slide the offsets and tip along the null space to the
        minimum norm point, keep the axes, and accept only if every training tip stays put. Used
        for reporting only."""
        off = np.r_[0: 3 * self.n, 6 * self.n: 6 * self.n + 3]
        # null space of the offset columns alone: an SVD of the full Jacobian mixes these trades
        # with axis rescalings, and dropping the axis part of such a mix is no longer invisible
        null_off = self._null_basis(J[:, off])
        if null_off.shape[1] == 0:
            return p
        cand = p.copy()
        cand[off] = p[off] - null_off @ (null_off.T @ p[off])  # minimum norm point on that subspace
        if np.abs(self._fk(cand, Q, self.types) - self._fk(p, Q, self.types)).max() > self.SAME_TIPS:
            return p  # the null space here was not exact; keep the fit as it is
        return cand

    def _identifiability(self, Q, J, null):
        """Per reported link: can the training motions pin its length? A link is not identifiable
        when a real share of its length direction lies in the near null space of the data Jacobian
        and pushing its length PROBE_DL along it moves no training tip by TIP_TOL. Examples: the
        height of a SCARA's vertical link, or an arm's first link, which trades off against the
        unknown base height."""
        p = self.report_params
        offs, _, tip = self._unpack(p)
        links = [(slice(3 * i, 3 * i + 3), offs[i]) for i in range(1, self.n)]
        links.append((slice(6 * self.n, 6 * self.n + 3), tip))
        out = []
        for idx, v in links:
            grow = np.zeros(p.size)
            grow[idx] = v / (np.linalg.norm(v) + 1e-12)  # gradient of this link's length
            move = null @ (null.T @ grow)                 # the part of "grow it" the data cannot see
            if np.linalg.norm(move) < self.NULL_SHARE:  # length is pinned to first order
                out.append(True)
                continue
            step = move * (self.PROBE_DL / (move @ grow))  # length changes by about PROBE_DL
            # first order tip change, not a re-run of _fk: weakly seen directions that share the null
            # space curve away and would make an invisible length look visible
            shift = np.linalg.norm((J @ step).reshape(-1, 3), axis=1).max()
            out.append(bool(shift >= self.TIP_TOL))
        return out

    @property
    def warm_state(self):
        if self.tree:
            return (self.params.copy(), list(self.types), [list(limb) for limb in self.limbs])
        return (self.params.copy(), list(self.types), list(self.order))

    def predict(self, Q):
        if self.tree:
            return self._fk_tree(self.params, np.atleast_2d(np.asarray(Q, float)))
        return self._fk(self.params, np.atleast_2d(Q)[:, self.order])

    def _by_channel(self, xs):
        out = [None] * self.n
        for i, c in enumerate(self.order):
            out[c] = xs[i]
        return out

    def axes_letters(self):
        """Read back which axis each joint is closest to: an interpretable discovery."""
        _, angs, _ = self._unpack(self.params)
        return ["xyz"[int(np.argmax(np.abs(a)))] for a in angs]

    def tokens(self):
        """Structure in channel order."""
        if self.tree:
            return self._tree_tokens()
        return self._by_channel([t + a for t, a in zip(self.types, self.axes_letters())])

    def link_lengths(self):
        if self.tree:
            return self._tree_link_lengths()
        offs, _, tip = self._unpack(self.report_params)
        return [float(np.linalg.norm(o)) for o in offs[1:]] + [float(np.linalg.norm(tip))]

    def describe(self):
        if self.tree:
            structure = self.tokens()
            return {"family": self.family, "axes": self._tree_axes(), "types": list(self.types),
                    "structure": structure, "limbs": [list(l) for l in self.limbs],
                    "limb_structure": [[structure[c] for c in limb] for limb in self.limbs],
                    "links_m": [round(v, 3) for v in self.link_lengths()],
                    "identifiable": list(self.identifiable or [])}
        d = {"family": self.family, "axes": self._by_channel(self.axes_letters()),
             "types": self._by_channel(list(self.types)), "structure": self.tokens(),
             "links_m": [round(v, 3) for v in self.link_lengths()], "identifiable": list(self.identifiable or [])}
        if self.order != list(range(self.n)):
            d["chain_order"] = list(self.order)  # links_m and identifiable follow this order
        return d

    # ---- tree: one trunk, then a chain out to each fingertip ----------------------
    def _set_topology(self, limbs):
        """Store the trunk (common prefix of every limb) and each limb's private channels."""
        limbs = [[int(c) for c in limb] for limb in limbs]
        trunk = []
        if limbs and all(limbs):
            for col in zip(*limbs):
                if len(set(col)) != 1:
                    break
                trunk.append(int(col[0]))
        branches = []
        for limb in limbs:
            rest = limb[len(trunk):] if limb[:len(trunk)] == trunk else [c for c in limb if c not in trunk]
            branch, seen = [], set()
            for c in rest:
                c = int(c)
                if c not in trunk and c not in seen:
                    seen.add(c)
                    branch.append(c)
            branches.append(branch)
        # a channel that landed in two branches is trunk-level: keep the first copy only
        used = set(trunk)
        clean = []
        for branch in branches:
            keep = []
            for c in branch:
                if c not in used:
                    used.add(c)
                    keep.append(c)
            clean.append(keep)
        self.trunk = trunk
        self.branches = clean
        self.limbs = [list(trunk) + b for b in clean]
        self.seq = list(trunk) + [c for b in clean for c in b]
        self.index = {c: i for i, c in enumerate(self.seq)}
        self.n_tips = len(limbs)

    def _fk_tree(self, p, Q, types=None):
        """Fingertips, shape (M, n_tips, 3). Joint parameters follow self.seq, types are per channel."""
        types = types if types is not None else self.types
        n = len(self.seq)
        offs = p[:3 * n].reshape(n, 3)
        angs = p[3 * n:6 * n].reshape(n, 3)
        tips = p[6 * n:6 * n + 3 * self.n_tips].reshape(self.n_tips, 3)
        M = Q.shape[0]
        pos = np.zeros((M, 3))
        R = np.broadcast_to(np.eye(3), (M, 3, 3)).copy()

        def apply(ch, pos, R):
            i = self.index[ch]
            pos = pos + np.einsum("mij,j->mi", R, offs[i])
            if types[ch] == "h":
                axis = angs[i] / (np.linalg.norm(angs[i]) + 1e-9)
                R = np.einsum("mij,mjk->mik", R, _rot(axis, Q[:, ch]))
            else:
                pos = pos + np.einsum("mij,j->mi", R, angs[i]) * Q[:, ch:ch + 1]
            return pos, R

        for ch in self.trunk:
            pos, R = apply(ch, pos, R)
        out = []
        for b, branch in enumerate(self.branches):
            pth, r = pos.copy(), R.copy()
            for ch in branch:
                pth, r = apply(ch, pth, r)
            out.append(pth + np.einsum("mij,j->mi", r, tips[b]))
        return np.stack(out, axis=1)

    def _types_from(self, pattern):
        types = ["h"] * self.n
        for ch, tok in enumerate(pattern):
            types[ch] = _tok(tok)[0]
        return types

    def _init_tree(self, pattern, branch_dir="x"):
        """One parameter vector: per joint an offset and an axis, then one tip offset per fingertip."""
        toks = [_tok(t) for t in pattern]
        n = len(self.seq)
        offs = np.zeros((n, 3))
        angs = np.zeros((n, 3))
        firsts = [b[0] for b in self.branches if b]
        for i, ch in enumerate(self.seq):
            t = toks[ch]
            scale = 1.0 if t[0] == "h" else 0.06
            angs[i] = np.array(AX[t[1]]) * scale + self.rng.normal(0, 0.15 * scale, 3)
            if ch in self.trunk and self.trunk.index(ch) == 0:
                offs[i] = np.array([0.0, 0.0, 0.08])
            elif ch in self.trunk:
                offs[i] = np.array([0.0, 0.0, 0.10])
            elif ch in firsts:
                side = 1.0 if firsts.index(ch) % 2 == 0 else -1.0
                offs[i] = np.array([0.0, 0.10 * side, 0.0])
            else:
                offs[i] = np.array(AX[branch_dir]) * 0.12
            offs[i] = offs[i] + self.rng.normal(0, 0.01, 3)
        tips = [np.array(AX[branch_dir]) * 0.12 + self.rng.normal(0, 0.01, 3) for _ in self.branches]
        return np.concatenate([offs.ravel(), angs.ravel(), np.asarray(tips, float).ravel()])

    def _blind_topologies(self, n_tips):
        """Guesses used when nobody has grouped the channels: channel 0 shared, then random assignments."""
        out = []
        shared = [0] if self.n > n_tips else []
        rest = [i for i in range(self.n) if i not in shared]
        base = [list(shared) for _ in range(n_tips)]
        for i, ch in enumerate(rest):
            base[i % n_tips].append(ch)
        out.append(base)
        guard = 0
        while len(out) < self.restarts and guard < 40:
            guard += 1
            role = self.rng.integers(0, n_tips + 1, size=self.n)
            shared = [int(i) for i in range(self.n) if int(role[i]) == n_tips]
            limbs, ok = [], True
            for t in range(n_tips):
                priv = [int(i) for i in range(self.n) if int(role[i]) == t]
                if not shared and not priv:
                    ok = False
                limbs.append(shared + priv)
            if ok:
                out.append(limbs)
        return out[:self.restarts]

    def _warm_tree(self, warm, topo):
        if not isinstance(warm, tuple) or len(warm) < 3:
            return None
        params, types, extra = warm[0], list(warm[1]), warm[2]
        if len(types) != self.n or not isinstance(extra, list) or not extra or not isinstance(extra[0], (list, tuple)):
            return None
        if [list(map(int, limb)) for limb in extra] != [list(map(int, limb)) for limb in topo]:
            return None
        return np.asarray(params, float), types

    def _fit_tree(self, Q, X, patterns, warm, weights, limbs):
        """Least squares over offsets and axes, topology fixed when `limbs` is known."""
        Q = np.asarray(Q, float)
        X = np.asarray(X, float)
        self.tree = True
        self.n_tips = int(X.shape[1])
        self.order = list(range(self.n))
        w = np.ones(len(Q)) if weights is None else np.asarray(weights, float)
        pats = [p for p in (patterns or []) if len(p) == self.n]
        inits = []  # (topology, pattern or None, branch axis letter, warm pair or None)
        if limbs is not None:
            topo = limbs
            warmed = self._warm_tree(warm, topo)
            if warmed is not None:
                inits.append((topo, None, "x", warmed))
            for i, pat in enumerate(pats):
                inits.append((topo, pat, "x", None))
                if i == 0:
                    inits.append((topo, pat, "z", None))
            while len(inits) < self.restarts:
                inits.append((topo, self._random_structure(), str(self.rng.choice(["x", "z"])), None))
        else:
            for topo in self._blind_topologies(self.n_tips):
                inits.append((topo, self._random_structure(), str(self.rng.choice(list("xyz"))), None))
        if not inits:
            inits.append(([[i] for i in range(self.n)][:self.n_tips] or [list(range(self.n))],
                           self._random_structure(), "x", None))
        best = None
        self.trials = []
        sw = np.sqrt(w)[:, None, None]
        for topo, pat, direction, warmed in inits:
            self._set_topology(topo)
            if warmed is not None:
                p0, types = warmed
                if p0.size != 6 * len(self.seq) + 3 * self.n_tips:
                    continue
            else:
                p0 = self._init_tree(pat, branch_dir=direction)
                types = self._types_from(pat)
            def res(p, ty=types):
                return ((self._fk_tree(p, Q, ty) - X) * sw).ravel()
            try:
                r = least_squares(res, p0, method="trf", max_nfev=400)
            except Exception:
                continue
            pred = self._fk_tree(r.x, Q, types)
            e2 = np.sum((pred - X) ** 2, axis=-1)
            cost = float(np.sqrt(np.sum(w[:, None] * e2) / (np.sum(w) * e2.shape[1])))
            self.trials.append((cost, "".join(types)))
            if best is None or cost < best[0]:
                best = (cost, r.x.copy(), list(types), [list(l) for l in self.limbs], list(self.trunk),
                        [list(b) for b in self.branches], list(self.seq), dict(self.index))
        if best is None:
            raise RuntimeError("tree fit failed")
        (self.train_rmse, self.params, self.types, self.limbs, self.trunk, self.branches,
         self.seq, self.index) = best
        self.report_params = self.params
        self.identifiable = []
        self.tree = True
        self.n_tips = len(self.limbs)
        return self

    def _tree_axes(self):
        n = len(self.seq)
        angs = self.params[3 * n:6 * n].reshape(n, 3)
        letters = ["?"] * self.n
        for ch, i in self.index.items():
            letters[ch] = "xyz"[int(np.argmax(np.abs(angs[i])))]
        return letters

    def _tree_tokens(self):
        axes = self._tree_axes()
        return [(self.types[c] if self.types[c] in "hs" else "?") + axes[c] for c in range(self.n)]

    def _tree_link_lengths(self):
        n = len(self.seq)
        offs = self.params[:3 * n].reshape(n, 3)
        tips = self.params[6 * n:6 * n + 3 * self.n_tips].reshape(self.n_tips, 3)
        return ([float(np.linalg.norm(o)) for o in offs[1:]] + [float(np.linalg.norm(t)) for t in tips])


class GMMModel(SelfModel):
    """Joint density over [q, x] (Kitchin 2025). Supports conditional sampling of q given x."""

    family = "gmm"

    def __init__(self, n: int, seed: int = 0):
        self.n = n
        self.seed = seed
        self.gmm = None

    def fit(self, Q, X, **_):
        X = np.asarray(X, float)
        self._out_shape = X.shape[1:] if X.ndim == 3 else None
        rows = X if X.ndim == 2 else X.reshape(len(X), -1)
        self._xd = rows.shape[1]
        Z = np.hstack([Q, rows * 10.0])  # scale x (metres) to radian-ish units
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
        d = getattr(self, "_xd", 3)
        cm, _, resp = self._condition(Q, list(range(n)), list(range(n, n + d)))
        y = np.einsum("mk,mkd->md", resp, cm) / 10.0
        shape = getattr(self, "_out_shape", None)
        return y if shape is None else y.reshape((y.shape[0],) + tuple(shape))

    def sample_inverse(self, x, n_samples=32, rng=None):
        """Many joint configurations that could reach x: the redundant IK answer."""
        rng = rng or np.random.default_rng(self.seed)
        n = self.n
        cm, cc, resp = self._condition(np.atleast_2d(x) * 10.0, list(range(n, n + 3)), list(range(n)))
        ks = rng.choice(len(resp[0]), size=n_samples, p=resp[0])
        return np.array([rng.multivariate_normal(cm[0, k], cc[k]) for k in ks])

    def density(self, Q, X):
        X = np.asarray(X, float)
        rows = X if X.ndim == 2 else X.reshape(len(X), -1)
        return self.gmm.score_samples(np.hstack([Q, rows * 10.0]))


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
        X = np.asarray(X, float)
        self._out_shape = X.shape[1:] if X.ndim == 3 else None
        rows = X if X.ndim == 2 else X.reshape(len(X), -1)
        self.net.fit(self._f(Q), rows * 10.0)
        return self

    def predict(self, Q):
        y = self.net.predict(self._f(Q)) / 10.0
        shape = getattr(self, "_out_shape", None)
        return y if shape is None else y.reshape((y.shape[0],) + tuple(shape))


FAMILIES = {"chain": ChainModel, "gmm": GMMModel, "mlp": MLPModel}
