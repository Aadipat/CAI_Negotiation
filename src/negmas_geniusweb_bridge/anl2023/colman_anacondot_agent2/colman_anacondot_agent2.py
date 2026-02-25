import csv
import logging
from random import randint
from time import time
from typing import cast, Set
import random
from decimal import Decimal
import numpy as np
import pandas as pd

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


class ColmanAnacondotAgent2(DefaultParty):
    """
    Template of a Python geniusweb agent.
    """

    def __init__(self):
        super().__init__()
        self.bids = []
        self.progress_time_array = []
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

        self.past_session_times = []

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
        elif isinstance(data, Settings):
            self.handle_settings(cast(Settings, data))

        elif isinstance(data, ActionDone):
            self.handle_action_done(cast(ActionDone, data))
        elif isinstance(data, Finished):
            self.handle_finished()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            self.save_data()
            # terminate the agent MUST BE CALLED
            self.logger.log(logging.INFO, "party is terminating:")
            super().terminate()
        else:
            self.logger.log(logging.WARNING, "Ignoring unknown info " + str(data))

    def handle_settings(self, settings: Settings):
        """Handle settings information."""
        self.settings = settings
        self.me = self.settings.getID()
        self.progress = self.settings.getProgress()
        self.parameters = self.settings.getParameters()
        self.storage_dir = self.parameters.get("storage_dir")
        profile_connection = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )
        self.profile = profile_connection.getProfile()
        self.domain = self.profile.getDomain()
        profile_connection.close()

    def handle_action_done(self, data: ActionDone):
        """Handle action done information."""
        action = data.getAction()
        actor = action.getActor()

        if actor != self.me:
            self.other = str(actor).rsplit("_", 1)[0]
            self.opponent_action(action)

    def handle_finished(self):
        """Handle finished information."""
        self.save_data()
        self.update_past_session_times()
        self.logger.log(logging.INFO, "party is terminating:")
        super().terminate()

    def update_past_session_times(self):
        """Update the list of past session times."""
        current_time = self.progress.get(time() * 1000)
        self.past_session_times.append(current_time)
        if len(self.past_session_times) > 10:
            self.past_session_times.pop(0)

    def getCapabilities(self) -> Capabilities:
        """MUST BE IMPLEMENTED
        Method to indicate to the protocol what the capabilities of this agent are.
        Leave it as is for the ANL 2023 competition

        Returns:
            Capabilities: Capabilities representation class
        """
        return Capabilities(
            {"SAOP"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
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
        return "colman agent for ANL 2023 competition"

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

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        # check if the last received offer is good enough
        print(f"my_turn: last_received_bid: {self.last_received_bid}")
        progress_turn = self.progress.get(time() * 1000)
        self.progress_time_array.append(progress_turn)
        if self.accept_condition(self.last_received_bid):
            # if so, accept the offer
            self.bids.append(self.last_received_bid)

            action = Accept(self.me, self.last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self.find_bid()
            self.bids.append(bid)
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
        # append new data to existing bids.csv file
        with open(f"{self.storage_dir}/bids.csv", "a") as f:
            writer = csv.writer(f)
            if f.tell() == 0:
                # if the file is empty, write the header row
                writer.writerow(["bid", "utility", "time_pressure_factor"])
            for bid, Time in zip(self.bids, self.progress_time_array):
                writer.writerow([bid, self.profile.getUtility(bid), Time])
                print(f"bid: {bid}, utility: {self.profile.getUtility(bid)}, time_pressure_factor: {Time}")

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False

        utility = self.profile.getUtility(bid)
        if len(self.past_session_times) > 10:
            avg_past_session_time = np.mean(self.past_session_times)
            time_pressure_factor = min(0.8, self.progress.get(time() * 1000) / avg_past_session_time)
        else:
            time_pressure_factor = self.progress.get(time() * 1000)

        acceptance_threshold = self.calculate_acceptance_threshold(time_pressure_factor)
        print(f"time_pressure_factor: {time_pressure_factor}")
        print(f"acceptance_threshold: {acceptance_threshold}")
        print(f"utility: {utility}")
        # check if the received bid is above the acceptance threshold
        if utility <= 0.75 and time_pressure_factor > 0.91:
            return False
        elif utility > acceptance_threshold:
            # if the time pressure is low or the utility of the bid is above the acceptance threshold, accept the bid
            if time_pressure_factor < 0.8 and utility >= acceptance_threshold:
                return True
            else:
                # if the time pressure is high and the utility of the bid is below the acceptance threshold, reject the bid
                return False

    def calculate_acceptance_threshold(self, progress: float) -> float:
        # Adjust parameters to fit your specific strategy
        op_model = self.opponent_model
        print(f"op_model: {op_model}")
        if op_model is not None:
            op_model.update(self.last_received_bid)
            prediction = op_model.get_predicted_utility(self.last_received_bid)
            print(f"prediction: {prediction}")
        initial_threshold = 0.9
        final_threshold = 0.75
        if prediction > final_threshold:
            final_threshold = prediction
        return initial_threshold + (final_threshold - initial_threshold) * progress

    def find_bid(self) -> Bid:
        all_bids = AllBidsList(self.profile.getDomain())

        best_bid_score = 0.0
        best_bid = None

        for _ in range(1500):
            bid = all_bids.get(randint(0, all_bids.size() - 1))
            bid_score = self.score_bid(bid)
            if bid_score > best_bid_score:
                best_bid_score, best_bid = bid_score, bid

        return best_bid

    def score_bid(self, bid: Bid, alpha: float = 0.95, eps: float = 0.1) -> float:
        progress = self.progress.get(time() * 1000)

        our_utility = float(self.profile.getUtility(bid))
        time_pressure = 1.0 - progress ** (1 / eps)
        score = alpha * time_pressure * our_utility

        if self.opponent_model is not None:
            opponent_utility = self.opponent_model.get_predicted_utility(bid)
            opponent_score = (1.0 - alpha * time_pressure) * opponent_utility
            score += opponent_score

        return score
