"""
Tennis backward induction engine for BO3 match states.

## Point encoding

`points_a` and `points_b` have two different semantics depending on context:

**Regular game** (``is_tiebreak=False``):
  ``points_a`` = SERVER's score in the current game,
  ``points_b`` = RECEIVER's score.

  * When A is serving (``is_a_serving=True``):
    ``points_a`` = A's score, ``points_b`` = B's score.
  * When B is serving (``is_a_serving=False``):
    ``points_a`` = B's score (server), ``points_b`` = A's score (receiver).

  Game win condition (for the server): ``points_a >= 4`` and
  ``points_a - points_b >= 2``.  Receiver wins analogously.
  At 3-3 (deuce) the score is normalised back to (3, 3).

**Tiebreak** (``is_tiebreak=True``):
  ``points_a`` = A's absolute tiebreak score,
  ``points_b`` = B's absolute tiebreak score.

  Win condition: first to 7 with a 2-point lead.

``games_a``, ``games_b``, ``sets_a``, ``sets_b`` always track player A and player B.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class MatchState:
    """Immutable representation of a tennis match state (BO3).

    See module docstring for the dual encoding of ``points_a`` / ``points_b``.
    """

    sets_a: int = 0
    sets_b: int = 0
    games_a: int = 0
    games_b: int = 0
    # regular game: server / receiver points; tiebreak: A / B absolute points
    points_a: int = 0
    points_b: int = 0
    is_a_serving: bool = True
    is_tiebreak: bool = False

    def key(self) -> Tuple:
        """Return a hashable tuple suitable for use as a dict key."""
        return (
            self.sets_a,
            self.sets_b,
            self.games_a,
            self.games_b,
            self.points_a,
            self.points_b,
            self.is_a_serving,
            self.is_tiebreak,
        )

    def is_terminal(self) -> bool:
        """True when either player has won 2 sets (BO3 complete)."""
        return self.sets_a == 2 or self.sets_b == 2


def _tiebreak_server(
    is_a_serving_at_tiebreak_start: bool,
    total_points_played: int,
) -> bool:
    """
    Return True if A is serving the NEXT tiebreak point.

    Tiebreak serve pattern (by number of points already played):
      point 0        : original server (1 point)
      points 1-2     : other player (2 points)
      points 3-4     : original server (2 points)
      points 5-6     : other player (2 points)
      ...

    For index n >= 1: block = (n-1) // 2.
    Original server serves on odd blocks.
    """
    if total_points_played == 0:
        return is_a_serving_at_tiebreak_start

    block = (total_points_played - 1) // 2
    original_serves_this_block = (block % 2 == 1)
    if original_serves_this_block:
        return is_a_serving_at_tiebreak_start
    else:
        return not is_a_serving_at_tiebreak_start


def next_state(state: MatchState, a_wins_point: bool) -> MatchState:
    """
    Advance the match state by one point.

    ``a_wins_point=True``  → player A wins the point.
    ``a_wins_point=False`` → player B wins the point.

    See module docstring for the ``points_a`` / ``points_b`` encoding.
    """
    if state.is_terminal():
        return state

    pa = state.points_a
    pb = state.points_b
    ga = state.games_a
    gb = state.games_b
    sa = state.sets_a
    sb = state.sets_b
    serving = state.is_a_serving
    tiebreak = state.is_tiebreak

    if tiebreak:
        # ---------------------------------------------------------------- #
        # Tiebreak: points_a = A's absolute count, points_b = B's.         #
        # First to 7 with 2+ lead wins the set.                            #
        # ---------------------------------------------------------------- #
        if a_wins_point:
            pa += 1
        else:
            pb += 1

        total_played = pa + pb  # total tiebreak points played after this one

        a_wins_tb = pa >= 7 and (pa - pb) >= 2
        b_wins_tb = pb >= 7 and (pb - pa) >= 2

        if a_wins_tb or b_wins_tb:
            if a_wins_tb:
                sa += 1
            else:
                sb += 1
            ga, gb, pa, pb = 0, 0, 0, 0
            tiebreak = False
            # Serve switches after the tiebreak set
            serving = not serving
        else:
            # Update who serves the next tiebreak point
            serving = _tiebreak_server(state.is_a_serving, total_played)

    else:
        # ---------------------------------------------------------------- #
        # Regular game: points_a = SERVER's points, points_b = RECEIVER's. #
        # Win: >= 4 points with 2+ lead. Deuce (3-3) resets equally.       #
        # ---------------------------------------------------------------- #

        # server_scores = True when the server wins the point
        server_scores = (a_wins_point == serving)

        if server_scores:
            pa += 1
        else:
            pb += 1

        # Deuce reset: if both are >= 3 and tied, normalise to (3, 3)
        if pa >= 3 and pb >= 3 and pa == pb:
            pa = 3
            pb = 3

        server_wins_game = pa >= 4 and (pa - pb) >= 2
        receiver_wins_game = pb >= 4 and (pb - pa) >= 2

        if server_wins_game or receiver_wins_game:
            if a_wins_point:
                ga += 1
            else:
                gb += 1
            pa, pb = 0, 0
            serving = not serving  # serve always switches after a game

            # Check set win
            a_wins_set = ga >= 6 and (ga - gb) >= 2
            b_wins_set = gb >= 6 and (gb - ga) >= 2

            if a_wins_set:
                sa += 1
                ga, gb = 0, 0
            elif b_wins_set:
                sb += 1
                ga, gb = 0, 0
            elif ga == 6 and gb == 6:
                tiebreak = True

    return MatchState(
        sets_a=sa,
        sets_b=sb,
        games_a=ga,
        games_b=gb,
        points_a=pa,
        points_b=pb,
        is_a_serving=serving,
        is_tiebreak=tiebreak,
    )


# ---------------------------------------------------------------------------
# Closed-form helpers used by build_win_prob_table to avoid infinite recursion
# ---------------------------------------------------------------------------

def _p_server_wins_game(ps: int, pr: int, p: float) -> float:
    """
    P(server wins the regular game) given (ps, pr) = (server pts, receiver pts)
    and p = P(server wins a point).

    Handles deuce/advantage analytically.
    """
    # Closed form at deuce or advantage: p_deuce = p^2 / (p^2 + q^2)
    if ps >= 3 and pr >= 3:
        q = 1.0 - p
        p_deuce = (p * p) / (p * p + q * q) if (p * p + q * q) > 0 else 0.5
        if ps == pr:
            return p_deuce
        elif ps > pr:  # server has advantage
            return p + q * p_deuce
        else:           # receiver has advantage
            return p * p_deuce

    def _recurse(ps_: int, pr_: int) -> float:
        if ps_ >= 4 and (ps_ - pr_) >= 2:
            return 1.0
        if pr_ >= 4 and (pr_ - ps_) >= 2:
            return 0.0
        if ps_ >= 3 and pr_ >= 3:
            return _p_server_wins_game(ps_, pr_, p)  # use closed form
        return p * _recurse(ps_ + 1, pr_) + (1.0 - p) * _recurse(ps_, pr_ + 1)

    return _recurse(ps, pr)


def _p_a_wins_tiebreak(pa: int, pb: int, p: float) -> float:
    """
    P(A wins the tiebreak) given (pa, pb) = A's and B's tiebreak points and
    p = P(A wins a point) (treated as constant for the closed-form calculation).

    Handles tiebreak deuce/advantage analytically.
    """
    # Closed form once both reach >= 6 and are tied
    if pa >= 6 and pb >= 6:
        q = 1.0 - p
        p_deuce = (p * p) / (p * p + q * q) if (p * p + q * q) > 0 else 0.5
        if pa == pb:
            return p_deuce
        elif pa > pb:
            return p + q * p_deuce
        else:
            return p * p_deuce

    def _recurse(pa_: int, pb_: int) -> float:
        if pa_ >= 7 and (pa_ - pb_) >= 2:
            return 1.0
        if pb_ >= 7 and (pb_ - pa_) >= 2:
            return 0.0
        if pa_ >= 6 and pb_ >= 6:
            return _p_a_wins_tiebreak(pa_, pb_, p)  # use closed form
        return p * _recurse(pa_ + 1, pb_) + (1.0 - p) * _recurse(pa_, pb_ + 1)

    return _recurse(pa, pb)


def _state_after_game(state: MatchState, a_wins: bool) -> MatchState:
    """
    Return the MatchState at the start of the NEXT game after the current one ends.

    ``a_wins=True`` means A wins the current game; ``a_wins=False`` means B wins.
    Points are reset; serve switches.
    """
    ga = state.games_a + (1 if a_wins else 0)
    gb = state.games_b + (0 if a_wins else 1)
    sa = state.sets_a
    sb = state.sets_b
    serving = not state.is_a_serving  # serve switches after each game
    tiebreak = False

    a_wins_set = ga >= 6 and (ga - gb) >= 2
    b_wins_set = gb >= 6 and (gb - ga) >= 2

    if a_wins_set:
        sa += 1
        ga, gb = 0, 0
    elif b_wins_set:
        sb += 1
        ga, gb = 0, 0
    elif ga == 6 and gb == 6:
        tiebreak = True

    return MatchState(
        sets_a=sa,
        sets_b=sb,
        games_a=ga,
        games_b=gb,
        points_a=0,
        points_b=0,
        is_a_serving=serving,
        is_tiebreak=tiebreak,
    )


def build_win_prob_table(p_a: float, p_b: float) -> Dict[Tuple, float]:
    """
    Build a complete win-probability table via backward induction / memoization.

    Parameters
    ----------
    p_a : float
        P(A wins a point) when A is serving.
    p_b : float
        P(B wins a point) when B is serving.

    Returns
    -------
    dict mapping ``state.key()`` → P(A wins the match from that state).

    When A is serving: ``p_point = p_a`` (prob A wins next point).
    When B is serving: ``p_point = 1 - p_b`` (prob A wins next point).

    Regular game states are computed at the **game level** (using closed-form
    intra-game probability) to avoid infinite recursion from deuce cycles.
    Tiebreak states inside the table are computed using the closed-form
    tiebreak deuce formula.
    """
    cache: Dict[Tuple, float] = {}

    def win_prob(state: MatchState) -> float:
        k = state.key()
        if k in cache:
            return cache[k]

        # Base cases
        if state.sets_a == 2:
            cache[k] = 1.0
            return 1.0
        if state.sets_b == 2:
            cache[k] = 0.0
            return 0.0

        if state.is_tiebreak:
            # Tiebreak: use closed-form for the entire remaining tiebreak,
            # then recurse on the post-tiebreak game-level states.
            # p_point_a is treated as constant for the tiebreak closed-form.
            p_point_a = p_a if state.is_a_serving else (1.0 - p_b)

            pa = state.points_a
            pb = state.points_b

            # P(A wins tiebreak from current score)
            p_a_wins_tb = _p_a_wins_tiebreak(pa, pb, p_point_a)

            # Post-tiebreak states (games reset, sets increment)
            state_a_wins = MatchState(
                sets_a=state.sets_a + 1,
                sets_b=state.sets_b,
                games_a=0,
                games_b=0,
                points_a=0,
                points_b=0,
                is_a_serving=not state.is_a_serving,
                is_tiebreak=False,
            )
            state_b_wins = MatchState(
                sets_a=state.sets_a,
                sets_b=state.sets_b + 1,
                games_a=0,
                games_b=0,
                points_a=0,
                points_b=0,
                is_a_serving=not state.is_a_serving,
                is_tiebreak=False,
            )

            prob = p_a_wins_tb * win_prob(state_a_wins) + \
                   (1.0 - p_a_wins_tb) * win_prob(state_b_wins)
            cache[k] = prob
            return prob

        else:
            # Regular game: use closed-form for intra-game, recurse at game level.
            # p_server = prob the CURRENT SERVER wins a point
            p_server = p_a if state.is_a_serving else p_b

            # P(server wins the current game from this score)
            p_sv_wins_game = _p_server_wins_game(
                state.points_a, state.points_b, p_server
            )

            # P(A wins this game)
            p_a_wins_game = p_sv_wins_game if state.is_a_serving else (1.0 - p_sv_wins_game)

            # States after this game ends
            state_after_a = _state_after_game(state, a_wins=True)
            state_after_b = _state_after_game(state, a_wins=False)

            prob = p_a_wins_game * win_prob(state_after_a) + \
                   (1.0 - p_a_wins_game) * win_prob(state_after_b)
            cache[k] = prob
            return prob

    # Seed with the initial state; memoization fills the rest bottom-up lazily
    win_prob(MatchState())

    # Ensure explicit terminal states are present
    cache[MatchState(sets_a=2).key()] = 1.0
    cache[MatchState(sets_b=2).key()] = 0.0

    return cache
