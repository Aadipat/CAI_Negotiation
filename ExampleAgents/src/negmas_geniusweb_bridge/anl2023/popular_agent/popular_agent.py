import datetime
import json
import logging
from math import floor
from random import randint
import time
from decimal import Decimal
from os import path
from typing import cast
import math

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
from geniusweb.issuevalue.Value import Value
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import (
    LinearAdditiveUtilitySpace,
)
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters

from .utils.opponent_model import OpponentModel
from geniusweb.issuevalue.Bid import Bid


class PopularAgent(DefaultParty):

    def __init__(self):
        super().__init__()

        self.domain: Domain = None
        self.parameters: Parameters = None
        self.profile: LinearAdditiveUtilitySpace = None
        self.progress: ProgressTime = None
        self.me: PartyId = None
        self.other: PartyId = None
        self.other_name: str = None
        self.settings: Settings = None
        self.storage_dir: str = None
        self.data_dict: dict = {}

        self.last_received_bid: Bid = None
        self.opponent_model: OpponentModel = None
        self.opponent_best_bid: Bid = None
        self.final_utility: float = 0

        self.all_bids_list: AllBidsList = None
        self.all_bids_size: int = 0
        self.bids_utilities: list[tuple[Bid, float]] = None
        self.num_of_top_bids: int = 1
        self.exposure_bids: float = 0.001
        self.accept_threshold: float = 1
        self.light_accept_threshold: float = 1

        self.times: list[Decimal] = []
        self.last_time = None
        self.avg_time = None

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
            self.all_bids_list = AllBidsList(self.domain)
            self.all_bids_size = self.all_bids_list.size()
            self.bids_utilities = self.get_bids_with_scores()
            profile_connection.close()

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()
            actor = action.getActor()

            # ignore action if it is our action
            if actor != self.me:
                self.other_name = str(actor).rsplit("_", 1)[0]
                data_path = f"{self.storage_dir}/{self.other_name}.json"
                if path.exists(data_path):
                    with open(data_path) as f:
                        self.data_dict = json.load(f)
                else:
                    self.data_dict = {"utility_per_session": []}

                failures = len(list([session == 0 for session in self.data_dict["utility_per_session"]]))
                self.accept_threshold = 0 if failures < 2 else 1
                self.light_accept_threshold = 0 if failures < 1 else 1
                bad_utility = len(list([float(session) < 0.5 for session in self.data_dict["utility_per_session"]]))
                self.exposure_bids = 0.003 if bad_utility < 1 else min(0.003*bad_utility, 0.05)

                # process action done by opponent
                self.opponent_action(action)
        # YourTurn notifies you that it is your turn to act
        elif isinstance(data, YourTurn):
            # execute a turn
            self.my_turn()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            agreements = cast(Finished, data).getAgreements()
            if len(agreements.getMap()) > 0:
                self.final_utility = float(self.profile.getUtility(agreements.getMap()[self.me]))
            self.data_dict["utility_per_session"].append(self.final_utility)
            self.save_data()

            # terminate the agent MUST BE CALLED
            super().terminate()

    def get_bids_with_scores(self) -> list:
        if self.bids_utilities is None:
            self.bids_utilities = []
            for index in range(self.all_bids_size):
                bid = self.all_bids_list.get(index)
                self.bids_utilities.append((bid, float(self.profile.getUtility(bid))))
            self.bids_utilities.sort(key=lambda x: x[1], reverse=True)

        return self.bids_utilities
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
        return "PopularAgent for the ANL 2023 competition"

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

            if not self.opponent_best_bid:
                self.opponent_best_bid = bid
            elif self.profile.getUtility(bid) > self.profile.getUtility(self.opponent_best_bid):
                self.opponent_best_bid = bid

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """

        if self.last_time is not None:
            self.times.append(datetime.datetime.now().timestamp() - self.last_time.timestamp())
            self.avg_time = sum(self.times[-3:]) / 3
        self.last_time = datetime.datetime.now()

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
        if self.other_name is not None:
            data_path = f"{self.storage_dir}/{self.other_name}.json"
            with open(data_path, "w") as f:
                json_data = json.dumps(self.data_dict)
                f.write(json_data)

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # progress of the negotiation session between 0 and 1 (1 is deadline)
        progress = self.progress.get(time.time() * 1000)
        threshold = 0.98
        light_threshold = 0.95

        if self.avg_time is not None:
            threshold = 1 - 1000 * self.accept_threshold * self.avg_time / self.progress.getDuration()
            light_threshold = 1 - 5000 * self.light_accept_threshold * self.avg_time / self.progress.getDuration()

        conditions = [
            progress >= threshold,
            self.profile.getUtility(bid) >= 0.9,
            progress > light_threshold and self.profile.getUtility(bid) >=
            self.bids_utilities[floor(len(self.bids_utilities) / 5) - 1][1]
        ]
        return any(conditions)

    def find_bid(self) -> Bid:
        if self.last_received_bid is None:
            return self.bids_utilities[0][0]

        progress = self.progress.get(time.time() * 1000)
        light_threshold = 0.95
        if self.avg_time is not None:
            light_threshold = 1 - 5000 * self.light_accept_threshold * self.avg_time / self.progress.getDuration()
        if progress > light_threshold:
            return self.opponent_best_bid

        self.num_of_top_bids = math.ceil(progress * self.exposure_bids * self.all_bids_list.size())
        rand_in_range = randint(0, self.num_of_top_bids)
        chosen_bid = self.bids_utilities[rand_in_range][0]

        return chosen_bid

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
        progress = self.progress.get(time.time() * 1000)

        our_utility = float(self.profile.getUtility(bid))

        time_pressure = 1.0 - progress ** (1 / eps)
        score = alpha * time_pressure * our_utility

        if self.opponent_model is not None:
            opponent_utility = self.opponent_model.get_predicted_utility(bid)
            opponent_score = (1.0 - alpha * time_pressure) * opponent_utility
            score += opponent_score

        return score


