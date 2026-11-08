"""Grain: one driver.

Teammate-adjusted driver strength, fitted with a Bradley-Terry model.

The problem this exists to solve: every all-time driver ranking that counts
wins is really a ranking of cars. A driver in the quickest car wins; the same
driver in the tenth-quickest does not. Wins measure the pairing, not the
person, and no amount of charting fixes that.

The one comparison the data does support is a driver against the other person
in the same garage. Same car, same upgrades, same strategy department, same
race. `fct_duel_coequipiers` already isolates that comparison. What it cannot
do on its own is compare two drivers who were never teammates, which is almost
all of them, and that is what this model adds.

How it works
------------
Bradley-Terry assigns every driver a positive strength p. The probability that
i finishes ahead of j in equal machinery is p_i / (p_i + p_j). Fitting those
strengths to the observed teammate results turns the teammate graph into a
single scale: A was teammates with B, B with C, C with D, so A and D become
comparable even though they never shared a garage and may be forty years
apart. The chain runs continuously from the 1950s to the current grid.

The fit uses the minorization-maximization iteration, which is the standard
solver for this likelihood and is guaranteed to increase it at every step:

    p_i  <-  W_i / sum_j ( n_ij / (p_i + p_j) )

W_i is i's total wins over teammates and n_ij the number of duels between i
and j.

Three things are done to keep the output honest
-----------------------------------------------
1. Regularisation. A driver who beat one teammate once, and never lost, has an
   unbounded maximum-likelihood strength. Every driver is therefore given two
   pseudo-duels, one won and one lost, against a virtual opponent pinned at
   average strength. This is a weak prior: it pulls thin records towards the
   middle and leaves long records essentially untouched.

2. Connected component. Strengths are only comparable within a connected piece
   of the teammate graph. Drivers whose careers never touch the main chain get
   a component label and are excluded from the published ranking rather than
   silently mixed in.

3. Uncertainty. The duels are resampled with replacement and the model refitted
   many times, giving a percentile interval for each driver. A driver with 300
   duels gets a tight interval; one with 40 gets a wide one, and the chart
   shows the difference instead of hiding it behind a single number.

What this does not claim
------------------------
It measures being faster than your teammate, which is not the same as being
the best driver. It cannot see a driver who was never beaten because they were
never in a competitive seat, it has no view of a teammate deliberately held
back, and it treats a 1952 duel and a 2026 duel as the same kind of event. It
also says nothing about reliability: duels where one car retired are excluded
upstream on purpose, because a broken gearbox is not a comment on pace.
"""
import numpy as np
import pandas as pd

# A driver needs this many duels before appearing in the published ranking.
# Below it the interval is so wide the number carries no information.
MIN_DUELS = 40

# Strength of the prior, in pseudo-duels won and lost against an average
# opponent. Two is weak enough to be invisible past ~50 real duels.
PRIOR = 1.0

N_BOOTSTRAP = 300
MAX_ITER = 2000
TOL = 1e-10


def _ajuster(gagne, prior=PRIOR, max_iter=MAX_ITER, tol=TOL, depart=None):
    """Fit Bradley-Terry strengths from a win-count matrix.

    `gagne[i, j]` is the number of times i finished ahead of j. Returns a
    strength vector normalised to a geometric mean of one.
    """
    n = gagne.shape[0]
    duels = gagne + gagne.T
    victoires = gagne.sum(axis=1) + prior

    # The virtual opponent is folded in as a constant: every driver has
    # `prior` duels against a player of strength 1.
    p = np.ones(n, dtype=np.float64) if depart is None else depart.copy()

    for _ in range(max_iter):
        # denom_i = sum_j n_ij / (p_i + p_j), plus the prior term.
        somme = p[:, None] + p[None, :]
        np.fill_diagonal(somme, 1.0)          # never divided by, avoids 0/0
        denom = (duels / somme).sum(axis=1) + 2.0 * prior / (p + 1.0)

        nouveau = victoires / denom
        nouveau /= np.exp(np.log(nouveau).mean())   # geometric mean -> 1

        ecart = np.abs(np.log(nouveau) - np.log(p)).max()
        p = nouveau
        if ecart < tol:
            break

    return p


def _composantes(duels):
    """Label the connected components of the teammate graph."""
    n = duels.shape[0]
    voisins = [np.flatnonzero(duels[i] > 0) for i in range(n)]
    label = np.full(n, -1, dtype=np.int64)
    courant = 0
    for depart in range(n):
        if label[depart] != -1:
            continue
        pile = [depart]
        label[depart] = courant
        while pile:
            x = pile.pop()
            for y in voisins[x]:
                if label[y] == -1:
                    label[y] = courant
                    pile.append(y)
        courant += 1
    return label


def model(dbt, session):
    dbt.config(materialized="table")

    duels = dbt.ref("fct_duel_coequipiers").df()

    # Each race pair is emitted once per driver, so keeping only the winning
    # side gives exactly one row per decided duel and no double counting.
    gagnants = duels.loc[
        duels["bat_coequipier_course"].astype(bool),
        ["pilote_id", "coequipier_id"],
    ].reset_index(drop=True)

    pilotes = pd.Index(
        sorted(set(gagnants["pilote_id"]) | set(gagnants["coequipier_id"]))
    )
    n = len(pilotes)
    gi = pilotes.get_indexer(gagnants["pilote_id"])
    pi = pilotes.get_indexer(gagnants["coequipier_id"])

    gagne = np.zeros((n, n), dtype=np.float64)
    np.add.at(gagne, (gi, pi), 1.0)

    matrice_duels = gagne + gagne.T
    label = _composantes(matrice_duels)
    principale = np.bincount(label).argmax()

    p = _ajuster(gagne)

    # Bootstrap over duels, not over drivers: the duel is the observation.
    tirages = np.empty((N_BOOTSTRAP, n), dtype=np.float64)
    rng = np.random.default_rng(20260501)
    m = len(gi)
    for b in range(N_BOOTSTRAP):
        pick = rng.integers(0, m, size=m)
        g = np.zeros((n, n), dtype=np.float64)
        np.add.at(g, (gi[pick], pi[pick]), 1.0)
        # Warm start from the full-data fit. The resampled likelihood is a
        # small perturbation of it, so this converges in tens of iterations
        # instead of hundreds and turns minutes of fitting into seconds.
        tirages[b] = _ajuster(g, max_iter=200, tol=1e-8, depart=p)

    bas = np.percentile(tirages, 5, axis=0)
    haut = np.percentile(tirages, 95, axis=0)

    # A log scale, so that a fixed gap always means the same odds: 400 points
    # is ten-to-one in equal machinery. 1500 is an arbitrary centre, chosen
    # because it reads as a rating rather than as a probability.
    def note(x):
        return 1500.0 + 400.0 * np.log10(x)

    sortie = pd.DataFrame({
        "pilote_id": pilotes,
        "force": p,
        "note": note(p),
        "note_basse": note(bas),
        "note_haute": note(haut),
        "nb_duels": matrice_duels.sum(axis=1),
        "nb_duels_gagnes": gagne.sum(axis=1),
        "composante": label,
        "dans_composante_principale": label == principale,
    })
    sortie["taux_duels"] = sortie["nb_duels_gagnes"] / sortie["nb_duels"]
    sortie["classable"] = (
        sortie["dans_composante_principale"] & (sortie["nb_duels"] >= MIN_DUELS)
    )
    sortie["incertitude"] = sortie["note_haute"] - sortie["note_basse"]
    sortie["rang"] = (
        sortie["note"].where(sortie["classable"]).rank(ascending=False, method="min")
    )
    return sortie
