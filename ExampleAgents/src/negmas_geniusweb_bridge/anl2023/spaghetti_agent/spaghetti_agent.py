import logging
from time import time
from typing import cast

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import (
    LinearAdditiveUtilitySpace,
)
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from tudelft_utilities_logging.ReportToLogger import ReportToLogger

from collections import deque
from .utils.opponent_model import OpponentModel
from .utils.accept import Acceptance
import numpy as np


class Agent37(DefaultParty):
    """
    We named our agent SpaghettiAgent
    Because everyone likes spaghetti and coding
    """

    def __init__(self):
        super().__init__()
        self.logger: ReportToLogger = self.getReporter()
        self.bid_history = []
        self.domain: Domain = None
        self.parameters: Parameters = None
        self.profile: LinearAdditiveUtilitySpace = None
        self.progress: ProgressTime = None
        self.me: PartyId = None
        self.other: str = None
        self.settings: Settings = None
        self.storage_dir: str = None
        self.target_utility = 0.9
        self.all_bids = None
        self.strategy_changed = False
        self.deque = deque()

        self.last_received_bid: Bid = None
        self.opponent_model: OpponentModel = None
        self.acceptance = Acceptance(self.bid_history, None, None)
        self.logger.log(logging.INFO, "party is initialized")

        self.exploring = True
        self.time_offset = 0
        self.window_bids = deque()
        self.opp_strategy = "random"

    def notifyChange(self, data: Inform):
        """MUST BE IMPLEMENTED
        This is the entry point of all interaction with your agent after is has been initialised.
        How to handle the received data is based on its class type.

        Args:
            info (Inform): Contains either a request for action or information.
        """

        # a Settings message is the first message that will be send to your
        # agent containing all the information about the negotiation session.
        if isinstance(data, Settings):
            self.settings = cast(Settings, data)
            self.me = self.settings.getID()

            # progress towards the deadline has to be tracked manually through the use of the Progress object
            self.progress = self.settings.getProgress()

            self.parameters = self.settings.getParameters()
            self.storage_dir = self.parameters.get("storage_dir")

            # the profile contains the preferences of the agent over the domain
            profile_connection = ProfileConnectionFactory.create(
                data.getProfile().getURI(), self.getReporter()
            )
            self.profile = profile_connection.getProfile()
            self.domain = self.profile.getDomain()
            self.acceptance.set_utility(self.profile.getUtility)
            profile_connection.close()

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()
            actor = action.getActor()

            # ignore action if it is our action
            if actor != self.me:
                # obtain the name of the opponent, cutting of the position ID.
                self.other = str(actor).rsplit("_", 1)[0]

                # process action done by opponent
                self.opponent_action(action)
        # YourTurn notifies you that it is your turn to act
        elif isinstance(data, YourTurn):
            # execute a turn
            self.my_turn()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            self.save_data()
            # terminate the agent MUST BE CALLED
            self.logger.log(logging.INFO, "party is terminating:")
            super().terminate()
        else:
            self.logger.log(logging.WARNING, "Ignoring unknown info " + str(data))

    def getCapabilities(self) -> Capabilities:
        """MUST BE IMPLEMENTED
        Method to indicate to the protocol what the capabilities of this agent are.
        Leave it as is for the ANL 2022 competition

        Returns:
            Capabilities: Capabilities representation class
        """
        return Capabilities(
            set(["SAOP"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    def send_action(self, action: Action):
        """Sends an action to the opponent(s)

        Args:
            action (Action): action of this agent
        """
        self.getConnection().send(action)

    # give a description of your agent
    def getDescription(self) -> str:
        """MUST BE IMPLEMENTED
        This is the agent of group 37

        Returns:
            str: Agent description
        """
        return "Spaghetti Agent"

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):
            # create opponent model if it was not yet initialised
            if self.opponent_model is None:
                self.opponent_model = OpponentModel(self.domain)
                self.acceptance.set_model(self.opponent_model)

            bid = cast(Offer, action).getBid()
            self.window_bids.append(bid)
            self.bid_history.append(bid)
            # update opponent model with bid
            self.opponent_model.update(bid)
            # set bid as last received
            self.last_received_bid = bid

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        self.find_opponent_strategy()
        bid = self.find_bid()

        # check if the last received offer is good enough
        if self.acceptance.accept_condition(
            self.last_received_bid, bid, self.progress.get(time() * 1000)
        ):
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
        else:
            # if not, find a bid to propose as counter offer

            action = Offer(self.me, bid)

        # send the action
        self.send_action(action)

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        data = "Data for learning (see README.md)"
        with open(f"{self.storage_dir}/data.md", "w") as f:
            f.write(data)

    ###########################################################################################
    ################################## Example methods below ##################################
    ###########################################################################################

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # progress of the negotiation session between 0 and 1 (1 is deadline)
        progress = self.progress.get(time() * 1000)

        # very basic approach that accepts if the offer is valued above 0.7 and
        # 95% of the time towards the deadline has passed
        conditions = [
            self.profile.getUtility(bid) > 0.8,
            progress > 0.95,
        ]
        return all(conditions)

    def find_opponent_strategy(self):
        if self.progress.get(time() * 1000) - self.time_offset < 0.2:
            return

        self.exploring = True
        self.time_offset = self.progress.get(time() * 1000)
        my_util_sum = 0
        my_util_square = 0
        increases = 0
        variance = 0

        for bid in self.window_bids:
            curr_util = self.profile.getUtility(bid)
            my_util_sum += curr_util
            my_util_square += curr_util**2

        util_avg = my_util_sum / len(self.window_bids)

        variance = (
            my_util_square
            - 2 * util_avg * my_util_sum
            + len(self.window_bids) * (util_avg) ** 2
        )
        variance = variance / len(self.window_bids)
        # print(variance, util_avg)
        if variance < 0.01:
            self.opp_strategy = "hardline"
        elif variance > 0.2:
            self.opp_strategy = "random"
        elif util_avg > 0.215:
            self.opp_strategy = "concede"
        else:
            self.opp_strategy = "tit-for-tat"
        self.strategy_changed = True
        self.window_bids = deque()

    def find_bid(self) -> Bid:
        # compose a list of all possible bids

        if len(self.deque) == 0 or self.strategy_changed:
            self.strategy_changed = False
            # Here is the result of the strategy that was used to generate
            domain = self.profile.getDomain()
            self.all_bids = self.generate_bids(domain)
            # Create a deque with 100 random samples from the generated bid list

            # Fallback if no bids match criteria
            if len(self.all_bids) == 0:
                all_bids_list = list(AllBidsList(domain))
                if all_bids_list:
                    self.all_bids = sorted(
                        all_bids_list,
                        key=lambda bid: self.profile.getUtility(bid),
                        reverse=True,
                    )[:10]  # Take top 10 bids

            sample = (
                list(
                    np.random.choice(
                        self.all_bids, min(100, len(self.all_bids)), replace=False
                    )
                )
                if len(self.all_bids) > 0
                else []
            )
            sample = sorted(
                sample, key=lambda bid: self.profile.getUtility(bid), reverse=True
            )
            self.deque = deque(sample)

        # Fallback to generating new bids if deque is empty
        if len(self.deque) == 0:
            domain = self.profile.getDomain()
            all_bids_list = list(AllBidsList(domain))
            if all_bids_list:
                return max(all_bids_list, key=lambda bid: self.profile.getUtility(bid))
            return None

        return self.deque.popleft()

    def generate_bids(self, domain):
        progress = self.progress.get(time() * 1000)
        # print(self.opp_strategy)
        if progress < 0.2:
            res = list(
                filter(
                    lambda bid: self.profile.getUtility(bid) > 0.9, AllBidsList(domain)
                )
            )
        elif self.opp_strategy == "random":
            res = list(
                filter(
                    lambda bid: self.profile.getUtility(bid) > 0.9, AllBidsList(domain)
                )
            )
        elif self.opp_strategy == "concede":
            res = list(
                filter(
                    lambda bid: self.profile.getUtility(bid) > 0.7
                    and self.opponent_model.get_predicted_utility(bid) > 0.5,
                    AllBidsList(domain),
                )
            )
        elif self.opp_strategy == "hardline":
            res = list(
                filter(
                    lambda bid: self.profile.getUtility(bid) > 0.8
                    and self.opponent_model.get_predicted_utility(bid) > 0.4,
                    AllBidsList(domain),
                )
            )
        else:
            res = list(
                filter(
                    lambda bid: self.profile.getUtility(bid) > 0.8
                    and self.opponent_model.get_predicted_utility(bid) > 0.5,
                    AllBidsList(domain),
                )
            )
        if len(res) == 0:
            res = list(
                filter(
                    lambda bid: self.profile.getUtility(bid) > 0.8, AllBidsList(domain)
                )
            )
        return res

    def score_bid(self, bid: Bid, alpha: float = 0.95, eps: float = 0.1) -> float:
        """Calculate heuristic score for a bid

        Args:
            bid (Bid): Bid to score
            alpha (float, optional): Trade-off factor between self interested and
                altruistic behaviour. Defaults to 0.95.
            eps (float, optional): Time pressure factor, balances between conceding
                and Boulware behaviour over time. Defaults to 0.1.

        Returns:
            float: score
        """
        progress = self.progress.get(time() * 1000)

        our_utility = float(self.profile.getUtility(bid))

        time_pressure = 1.0 - progress ** (1 / eps)
        score = alpha * time_pressure * our_utility

        if self.opponent_model is not None:
            opponent_utility = self.opponent_model.get_predicted_utility(bid)
            opponent_score = (1.0 - alpha * time_pressure) * opponent_utility
            score += opponent_score

        return score
