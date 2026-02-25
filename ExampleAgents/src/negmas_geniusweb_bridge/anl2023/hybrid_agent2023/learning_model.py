from .utils import *
from .opponent_model import OpponentModel
import os
import pickle
import numpy as np
from numpy.linalg import inv


class LearningModel:
    """
    Save only minimum observed utility.
    """

    profile: LinearAdditiveUtilitySpace
    progress: ProgressTime
    received_bids: list
    my_bids: list
    acceptance_time: float
    accepted_bid: Bid
    opponent_accepted: bool
    opponent_model: OpponentModel
    data: list
    moves_me: list
    moves_opp: list

    def __init__(
        self, profile: LinearAdditiveUtilitySpace, progress: ProgressTime, **kwargs
    ):
        self.profile = profile
        self.progress = progress
        self.received_bids = []
        self.my_bids = []
        self.opponent_model = kwargs["opponent_model"]
        self.data = []
        self.acceptance_time = -1
        self.opponent_accepted = False
        self.accepted_bid = None
        self.moves_me = []
        self.moves_opp = []

    def receive_bid(self, bid: Bid, **kwargs):
        if bid is not None:
            time = get_time(self.progress)

            self.received_bids.append([time, bid])

    def save_bid(self, bid: Bid, **kwargs):
        self.my_bids.append(bid)

    def reach_agreement(self, accepted_bid: Bid, opponent_accepted: bool, **kwargs):
        time = get_time(self.progress)

        self.accepted_bid = accepted_bid
        self.opponent_accepted = opponent_accepted
        self.acceptance_time = time

    def save_data(self, storage_dir: str, other: str, **kwargs):
        if other is None or storage_dir is None or len(self.received_bids) < 2:
            return

        domain_size = AllBidsList(self.profile.getDomain()).size()
        utilities = []
        times = []

        for t, bid in self.received_bids:
            utility = self.opponent_model.get_utility(bid)

            utilities.append(utility)
            times.append(t)

        p0 = max(utilities)
        p2 = min(utilities)

        try:

            def target_fn(t, utility):
                return (utility - (1 - t) * (1 - t) * p0 - t * t * p2) / (
                    2.0 * (1 - t) + 1e-12
                )

            target = [target_fn(times[i], utilities[i]) for i in range(len(utilities))]

            X = np.reshape(np.array(times, dtype=np.float32), (len(times), 1))
            Y = np.reshape(np.array(target, dtype=np.float32), (len(target), 1))

            p1 = float(inv((X.transpose().dot(X))).dot(X.transpose().dot(Y)))
        except:
            if len(self.data) > 0:
                p1 = float(np.mean([data["p1"] for data in self.data]))
            else:
                p1 = 0.80

        self.moves_me = self.get_moves(False)
        self.moves_opp = self.get_moves(True)

        correlation = calculate_move_correlation(self.moves_me, self.moves_opp)

        opponent_acceptance_time = (
            -1
            if not self.opponent_accepted or self.accepted_bid is None
            else self.acceptance_time
        )

        self.data.append(
            {
                "p0": p0,
                "p1": p1,
                "p2": p2,
                "domain_size": domain_size,
                "opponent_acceptance_time": opponent_acceptance_time,
                "correlation": correlation,
            }
        )

        with open(f"{storage_dir}/{other}_data.pkl", "wb") as f:
            pickle.dump(self.data, f)

    def load_data(self, storage_dir: str, other: str, **kwargs) -> list:
        self.data = []

        if storage_dir is None or other is None:
            return self.data

        if os.path.exists(f"{storage_dir}/{other}_data.pkl"):
            with open(f"{storage_dir}/{other}_data.pkl", "rb") as f:
                self.data = pickle.load(f)

        return self.data

    def get_moves(self, is_opp: bool) -> list:
        bids = [x[1] for x in self.received_bids] if is_opp else self.my_bids

        utility_me, utility_opp = [], []

        for bid in bids:
            utility_me.append(get_utility(self.profile, bid))
            utility_opp.append(self.opponent_model.get_utility(bid))

        moves = []

        for i in range(1, len(bids)):
            my_utility_change = utility_me[i] - utility_me[i - 1]
            opponent_utility_change = utility_opp[i] - utility_me[i - 1]

            moves.append(get_move(my_utility_change, opponent_utility_change))

        return moves
