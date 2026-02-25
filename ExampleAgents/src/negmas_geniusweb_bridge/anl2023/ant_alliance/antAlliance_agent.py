import logging
from random import randint
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

from .utils.opponent_model import OpponentModel
import numpy as np


class AntAllianceAgent(DefaultParty):
    """
    Template of a Python geniusweb agent.
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

        self.last_received_bid: Bid = None
        self.opponent_model: OpponentModel = None

        self.receivedBids = set()
        self.opponent_best_bid: Bid = None
        self.allMyBidsSorted: list = None
        self.numberOfIssues = 0
        self.bid_matrix = None
        self.issues_id_list: list = None
        self.issues_value_list: list = None
        self.issues_valueNum_list: list = None
        self.useBidList: list = None
        self.lastOfferBid: Bid = None
        self.goodBidsOfOpponent: list = None
        self.next_bid: Bid = None

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

            all_bids = AllBidsList(self.domain)
            self.allMyBidsSorted = list(all_bids)
            self.allMyBidsSorted.sort(reverse=True, key=self.profile.getUtility)

            self.init_bid_matrix()

            self.generate_useBidList()

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

                self.analysis_opponent_bids()

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
        Returns a description of your agent. 1 or 2 sentences.

        Returns:
            str: Agent description
        """
        return "Template agent for the ANL 2022 competition"

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
            self.receivedBids.add(bid)

            if self.opponent_best_bid is None:
                self.opponent_best_bid = bid
            elif self.profile.getUtility(bid) > self.profile.getUtility(
                self.opponent_best_bid
            ):
                self.opponent_best_bid = bid

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        # check if the last received offer is good enough
        if self.accept_condition(self.last_received_bid):
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
            self.send_action(action)
        else:
            # if not, find a bid to propose as counter offer
            self.get_social_bid()

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        data = "Data for learning (see README.md)"
        with open(f"{self.storage_dir}/data.md", "w") as f:
            f.write(data)

    def init_bid_matrix(self):
        self.numberOfIssues = len(self.domain.getIssuesValues())
        self.issues_id_list = []
        self.issues_value_list = []
        self.issues_valueNum_list = []
        maxNumberOfValues = 0
        for issue_id, issue_estimator in self.domain.getIssuesValues().items():
            self.issues_id_list.append(issue_id)
            value_list = []
            for issue_value in issue_estimator:
                value_list.append(issue_value)
            maxNumberOfValues = max(maxNumberOfValues, len(value_list))
            self.issues_value_list.append(value_list)
            self.issues_valueNum_list.append(len(value_list))

        self.bid_matrix = np.zeros((self.numberOfIssues, maxNumberOfValues), dtype=int)

    def analysis_opponent_bids(self):
        for (
            issue_id,
            issue_estimator,
        ) in self.last_received_bid.getIssueValues().items():
            row = self.issues_id_list.index(issue_id)
            column = self.issues_value_list[row].index(issue_estimator)
            self.bid_matrix[row][column] += 1
        # print(self.bid_matrix)

    def analysis_bid_matrix(self):
        maxValueIndex_list = []
        for row in range(self.numberOfIssues):
            maxIndex = 0
            maxValue = 0
            for column in range(self.issues_valueNum_list[row]):
                if self.bid_matrix[row][column] > maxValue:
                    maxValue = self.bid_matrix[row][column]
                    maxIndex = column
            maxValueIndex_list.append(maxIndex)
        # print(maxValueIndex_list)
        self.goodBidsOfOpponent = []

        for i in range(len(self.allMyBidsSorted)):
            bid = self.allMyBidsSorted[i]
            flagCount = 0
            for issue_id, issue_estimator in bid.getIssueValues().items():
                issueIndex = self.issues_id_list.index(issue_id)
                valueIndex = maxValueIndex_list[issueIndex]
                if issue_estimator == self.issues_value_list[issueIndex][valueIndex]:
                    flagCount += 1
            if flagCount >= max(1, self.numberOfIssues - 1):
                self.goodBidsOfOpponent.append(bid)

        for item in self.receivedBids:
            self.goodBidsOfOpponent.append(item)

    def generate_useBidList(self):
        bid_list = []
        for i in range(len(self.allMyBidsSorted)):
            bid = self.allMyBidsSorted[i]
            utility = self.profile.getUtility(bid)
            if utility > 0.75:
                bid_list.append(bid)
        # Fallback: if no bids above threshold, use all sorted bids
        if not bid_list and self.allMyBidsSorted:
            bid_list = list(self.allMyBidsSorted)
        self.useBidList = bid_list

    def get_social_bid(self):
        progress = self.progress.get(time() * 1000)

        if self.opponent_model is None:
            self.opponent_model = OpponentModel(self.domain)

        if progress < 0.5:
            # Fallback to best bid if useBidList is empty
            if not self.useBidList:
                bid = (
                    self.allMyBidsSorted[0]
                    if self.allMyBidsSorted
                    else self.lastOfferBid
                )
            else:
                index = randint(0, len(self.useBidList) - 1)
                bid = self.useBidList[index]
            self.next_bid = bid
        elif progress > 0.95:
            bid = self.opponent_best_bid
            self.next_bid = bid
        else:
            self.analysis_bid_matrix()

            share_bids_list = []
            for bid in self.goodBidsOfOpponent:
                if self.profile.getUtility(bid) >= 0.5:
                    share_bids_list.append(bid)

            max_utility = 0
            self.next_bid = self.lastOfferBid
            if len(share_bids_list) == 0:
                self.next_bid = self.lastOfferBid
            else:
                for bid in share_bids_list:
                    op_utility = self.opponent_model.get_predicted_utility(bid)
                    my_utility = float(self.profile.getUtility(bid))
                    social_welfare = op_utility + my_utility
                    if social_welfare > max_utility:
                        max_utility = social_welfare
                        self.next_bid = bid

        if self.next_bid is None:
            self.next_bid = self.allMyBidsSorted[0]

        action = Offer(self.me, self.next_bid)
        self.lastOfferBid = self.next_bid
        self.send_action(action)

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # progress of the negotiation session between 0 and 1 (1 is deadline)
        progress = self.progress.get(time() * 1000)

        conditions = [
            progress > 0.9 and self.profile.getUtility(bid) > 0.75,
            progress > 0.95 and self.profile.getUtility(bid) > 0.65,
        ]
        return any(conditions)
