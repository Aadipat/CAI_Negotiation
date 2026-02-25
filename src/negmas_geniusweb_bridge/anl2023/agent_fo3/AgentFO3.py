from decimal import Decimal
import logging
import json
import os
from random import randint
from time import time
from typing import cast, TypedDict

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from geniusweb.bidspace.Interval import Interval
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
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from tudelft_utilities_logging.ReportToLogger import ReportToLogger
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList

from .utils.opponent_model import OpponentModel


class SessionData(TypedDict):
    paretoCenter: float
    acceptUtility: float
    finishTime: float


class DataList(TypedDict):
    sessions: list[SessionData]


class AgentFO3(DefaultParty):
    """
    Template of a Python geniusweb agent.

    Note:
        Minor modification from original: Added fallback to best bid when no bids
        are found in the target utility range on small domains.
    """

    def __init__(self):
        super().__init__()
        self.logger: ReportToLogger = self.getReporter()

        self.domain: Domain = None
        self.parameters: Parameters = None
        self.profile: LinearAdditiveUtilitySpace = None
        self.progress: ProgressTime = None
        self.me: PartyId = None
        self.other: str = None
        self.settings: Settings = None
        self.storage_dir: str = None

        self.data_list: DataList = None
        self.accept_utility: float = 0
        self.accept_utility_history: list[float] = None
        self.pareto_center_history: list[float] = None
        self.finish_time_hisotry: list[float] = None
        self.calc_utility: list[float] = None
        self.time_flag: bool = True
        self.utility_average: float = 0.8
        self.finish_time_average: float = 0.95
        self.pareto_center: float = 1.0
        self.topbid_percentage: float = 0.01

        self.allbid: AllBidsList = None
        self.bid_with_utility: list[tuple[Bid, float]] = None
        self.topbid_num: int = None
        self.min_util: float = 0.95
        self.weak_accept_flag: bool = False
        self.op_best_bid: Bid = None

        self.last_received_bid: Bid = None
        self.opponent_model: OpponentModel = None
        self.logger.log(logging.INFO, "party is initialized")

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
            self.op_utility_log = []
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
            self.allbid = AllBidsList(self.domain)
            self.bids_all = BidsWithUtility.create(cast(LinearAdditive, self.profile))
            profile_connection.close()

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()
            actor = action.getActor()

            # ignore action if it is our action
            if actor != self.me:
                # obtain the name of the opponent, cutting of the position ID.
                if self.other is None:
                    # Use rsplit to safely handle names without underscores
                    actor_str = str(actor)
                    parts = actor_str.rsplit("_", 1)
                    self.other = parts[0] if len(parts) >= 1 else actor_str
                    self.load_data()

                # process action done by opponent
                self.opponent_action(action)
        # YourTurn notifies you that it is your turn to act
        elif isinstance(data, YourTurn):
            if self.progress.get(time() * 1000) >= 0.1 and self.time_flag:
                self.time_flag = False
                self.calc_data()
            # execute a turn
            self.my_turn()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            accept = cast(Finished, data).getAgreements()
            if len(accept.getMap()) > 0:
                self.accept_utility = float(
                    self.profile.getUtility(accept.getMap()[self.me])
                )
            self.update_data()
            self.save_data()
            # terminate the agent MUST BE CALLED
            self.logger.log(logging.INFO, "party is terminating:")
            super().terminate()
        else:
            self.logger.log(logging.WARNING, "Ignoring unknown info " + str(data))

    def load_data(self):
        if os.path.exists(f"{self.storage_dir}/{self.other}.json"):
            with open(f"{self.storage_dir}/{self.other}.json") as f:
                self.data_list = json.load(f)
            self.accept_utility_history = []
            self.pareto_center_history = []
            self.finish_time_hisotry = []
            for session in self.data_list["sessions"]:
                self.accept_utility_history.append(session["acceptUtility"])
                self.pareto_center_history.append(session["paretoCenter"])
                self.finish_time_hisotry.append(session["finishTime"])
        else:
            self.data_list = {"sessions": []}

    def calc_data(self):
        if self.accept_utility_history is None:
            return
        self.calc_utility = []
        for i in range(len(self.accept_utility_history)):
            x = self.pareto_center / self.pareto_center_history[i]
            self.calc_utility.append(self.accept_utility_history[i] * x)
        self.utility_average = sum(self.calc_utility) / len(self.calc_utility)
        self.finish_time_average = sum(self.finish_time_hisotry) / len(
            self.finish_time_hisotry
        )
        bad_util_num = sum([i < 0.5 for i in self.accept_utility_history])
        if (
            bad_util_num >= len(self.accept_utility_history) / 4
            and len(self.accept_utility_history) > 3
        ):
            self.weak_accept_flag = True
        if (
            bad_util_num > len(self.accept_utility_history) * 0.6
            and len(self.accept_utility_history) > 3
        ):
            self.topbid_percentage = 0.05
        elif bad_util_num > len(self.accept_utility_history) * 0.3:
            self.topbid_percentage = 0.025
        self.topbid_num = int(self.allbid.size() * self.topbid_percentage)

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
        Returns a description of your agent. 1 or 2 sentences.

        Returns:
            str: Agent description
        """
        return "AgentFO3"

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

            bid = cast(Offer, action).getBid()

            # update opponent model with bid
            self.opponent_model.update(bid)
            # set bid as last received
            self.last_received_bid = bid

            if self.op_best_bid is None:
                self.op_best_bid = bid
            elif self.profile.getUtility(self.op_best_bid) < self.profile.getUtility(
                bid
            ):
                self.op_best_bid = bid

            if self.progress.get(time() * 1000) <= 0.1:
                self.op_utility_log.append(self.profile.getUtility(bid))
                op_util_ave = sum(self.op_utility_log) / len(self.op_utility_log)
                self.pareto_center = float((3 + op_util_ave) / 4)

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        # check if the last received offer is good enough
        if self.accept_condition(self.last_received_bid):
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self.find_bid()
            action = Offer(self.me, bid)

        # send the action
        self.send_action(action)

    def update_data(self):
        finish_time = self.progress.get(time() * 1000)

        session_data: SessionData = {
            "paretoCenter": self.pareto_center,
            "acceptUtility": self.accept_utility,
            "finishTime": finish_time,
        }

        self.data_list["sessions"].append(session_data)

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        with open(f"{self.storage_dir}/{self.other}.json", "w") as f:
            json.dump(self.data_list, f, indent=4)

    ###########################################################################################
    ################################## Example methods below ##################################
    ###########################################################################################

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # progress of the negotiation session between 0 and 1 (1 is deadline)
        progress = self.progress.get(time() * 1000)
        utility = float(self.profile.getUtility(bid))

        conditions = [
            not self.time_flag and utility > self.pareto_center,
            utility >= self.min_util,
            min(0.8, self.finish_time_average) <= progress
            and utility > max(0.45, self.utility_average),
            progress >= min(0.9, self.finish_time_average)
            and self.weak_accept_flag
            and utility >= float(self.profile.getUtility(self.op_best_bid)),
            progress >= 0.98,
        ]
        return all(conditions)

    def find_bid(self) -> Bid:
        if self.bid_with_utility is None:
            self.bid_with_utility = []
            for i in range(self.allbid.size()):
                bid = self.allbid.get(i)
                util = self.profile.getUtility(bid)
                self.bid_with_utility.append((bid, util))
            self.bid_with_utility.sort(key=lambda tup: tup[1], reverse=True)
            self.topbid_num = max(1, int(self.allbid.size() * self.topbid_percentage))
            if self.topbid_num > 0 and len(self.bid_with_utility) >= self.topbid_num:
                self.min_util = self.bid_with_utility[self.topbid_num - 1][1]

        # Fallback to best bid if no bids available
        if not self.bid_with_utility:
            return self.op_best_bid

        if self.progress.get(time() * 1000) >= 0.98 and self.weak_accept_flag:
            return self.op_best_bid
        elif (
            min(0.85, self.finish_time_average) < self.progress.get(time() * 1000)
            and not self.topbid_percentage == 0.01
        ):
            op_max_util = self.profile.getUtility(self.op_best_bid)
            options: ImmutableList[Bid] = self.bids_all.getBids(
                Interval(op_max_util, self.min_util)
            )
            if options.size() == 0:
                # if we can't find good bid
                options = self.bids_all.getBids(Interval(self.min_util, 1))
            # pick a random one, fallback to best bid if empty
            if options.size() == 0:
                return self.bid_with_utility[0][0]
            return options.get(randint(0, options.size() - 1))

        # Ensure topbid_num is valid
        if self.topbid_num <= 0:
            return self.bid_with_utility[0][0]
        return self.bid_with_utility[randint(0, self.topbid_num - 1)][0]

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
