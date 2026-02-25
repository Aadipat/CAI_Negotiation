import logging
from random import randint
from time import time
from typing import cast
from math import exp

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

# from .utils.opponent_model import OpponentModel


class KB_time_diff_Agent(DefaultParty):
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

        self.sort_bids_dict: dict = None
        self.cnt: int = 0
        self.cnt2: int = 0
        self.cnt_progress: int = 0
        self.start_progress: float = 0
        self.end_progress: float = 0
        self.estimate_time_diff: float = (
            0.001  # To prevent the denominator from being zero when dividing
        )
        self.bidding_time: float = 0.9  # turning point begining to compromise

        self.opponent_offers = []  # the list of opponent offers

        self.last_received_bid: Bid = None
        # self.opponent_model: OpponentModel = None # not use opponent model
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
            self.all_bids = AllBidsList(self.domain)

            self.sort_bids_dict = self.sort_bids_dic_for_acceptance()  # add

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
            self.cnt += 1
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
        Leave it as is for the ANL 2023 competition

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
        return "KB_time_diff_Agent for the ANL 2023 competition"

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):
            # create opponent model if it was not yet initialised
            # if self.opponent_model is None:
            #     self.opponent_model = OpponentModel(self.domain)

            bid = cast(Offer, action).getBid()

            progress = self.progress.get(time() * 1000)
            if progress < self.bidding_time:
                # update opponent model with bid until bidding_time
                self.update(bid)

            # set bid as last received
            self.last_received_bid = bid

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        self.decide_estimate_time_diff()

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

        # decide second_threshold
        second_threshold = 1 - self.estimate_time_diff
        # decide first_threshold
        first_threshold = self.decide_first_threshold(second_threshold)

        # progress of the negotiation session between 0 and 1 (1 is deadline)
        progress = self.progress.get(time() * 1000)

        if progress < first_threshold:
            # accepts if the offer is valued above accept_func(progress)
            condition = [self.profile.getUtility(bid) > self.accept_func(progress)]

        elif progress >= first_threshold and progress < second_threshold:
            # if bid is included in "opponent_offers" and the utility is above 0.3, accept
            # if the utility is above accept_func, accept
            condition = [
                bid in self.opponent_offers,
                self.profile.getUtility(bid) >= 0.3,
            ]  # parameter
            condition = [
                all(condition),
                self.profile.getUtility(bid) > self.accept_func(progress),
            ]

        else:
            # definitely accept
            condition = [True]

        return any(condition)

    def find_bid(self) -> Bid:
        progress = self.progress.get(time() * 1000)

        e_remain_num = self.estimate_remain_num(progress)

        if progress >= self.bidding_time or (
            e_remain_num <= 10 and self.cnt > 0
        ):  # parameter
            sort_bids_dict = self.sort_bids_dic_for_bidding()
            index = sort_bids_dict[self.cnt2][0]
            best_bid = self.opponent_offers[index]
            self.cnt2 += 1

            return best_bid

        else:
            # if bid utility is lower than accept_func(progress), initialize cnt
            if self.sort_bids_dict[self.cnt][1] < self.accept_func(progress):
                self.cnt = 0  # initialized

            best_bid = self.all_bids.get(self.sort_bids_dict[self.cnt][0])
            return best_bid

    def estimate_remain_num(self, progress: float) -> int:
        # Prevent division by zero on small domains
        if self.estimate_time_diff <= 0:
            self.estimate_time_diff = 0.001
        e_remain_num = int((1 - progress) / self.estimate_time_diff)
        return e_remain_num

    def score_bid(self, bid: Bid) -> float:
        our_utility = float(self.profile.getUtility(bid))

        return our_utility

    def accept_func(self, t: float) -> float:
        high_threshold = 0.90  # parameter
        low_threshold = 0.70  # parameter

        a = 10  # sharp or gentle  # defolt = 6

        based_sigmoid = -1 / (1 + exp(-a * (t - 0.5))) + 1

        y = based_sigmoid * (high_threshold - low_threshold) + low_threshold

        # print(t, y) # print time and result of func

        return y

    def sort_bids_dic_for_acceptance(self) -> dict:
        # sort bids score in ascending order using dict

        domain = self.profile.getDomain()
        all_bids = AllBidsList(domain)

        bids_dict = {}
        for i in range(all_bids.size() - 1):
            bid = all_bids.get(i)
            bids_dict[i] = self.score_bid(bid)

        sort_bids_dict = sorted(bids_dict.items(), key=lambda x: x[1], reverse=True)

        # print(sort_bids_dict)

        return sort_bids_dict

    def sort_bids_dic_for_bidding(self) -> Bid:
        bids_dict = {}
        for i in range(len(self.opponent_offers)):
            bid = self.opponent_offers[i]
            bids_dict[i] = self.score_bid(bid)

        sort_bids_dict = sorted(bids_dict.items(), key=lambda x: x[1], reverse=True)

        return sort_bids_dict

    # update the list including bids
    def update(self, bid: Bid) -> None:
        # keep track of all bids received
        self.opponent_offers.append(bid)

    def decide_estimate_time_diff(self) -> None:
        self.cnt_progress += 1
        # get the start time
        if (self.cnt_progress % 2) == 1:
            self.start_progress = self.progress.get(time() * 1000)
        # get the end time
        if (self.cnt_progress % 2) == 0:
            bias = 1.1  # parameter
            self.end_progress = self.progress.get(time() * 1000)

            self.estimate_time_diff = (self.end_progress - self.start_progress) * bias
            # print(self.estimate_time_diff)

    def decide_first_threshold(self, second_threshold: float) -> float:
        accept_time = 0.93  # parameter
        if second_threshold > accept_time:
            return accept_time

        else:
            if 1 - self.estimate_time_diff * 2 > 0:
                return 1 - self.estimate_time_diff * 2
            else:
                return second_threshold
