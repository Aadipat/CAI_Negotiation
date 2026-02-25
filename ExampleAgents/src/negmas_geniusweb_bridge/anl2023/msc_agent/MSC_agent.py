from enum import Enum
import logging
import os
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

from .opponent_model import OpponentModel
from .opponent_features import get_opponent_features
from .strategy import Strategy
from .sac import SAC
import numpy as np

class ProposePurpose(Enum):
    TO_PROPOSE = 0
    TO_RESPOND = 1

class MSCAgent(DefaultParty):
    _best = None  # The best outcome for me
    _max = 0  # The maximum of my utility function
    _thr_time = 0.96   # The threshold time for acceptance strategy
    _time_window = 10

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

        self.centroids = []
        self.strategies = []
        self.uoffers = [0.0] * self._time_window
        self.partner_uoffers = [0.0] * self._time_window
        self.partner_offers = []
        self.partner_utils = []
        self.current_opponent_feature = np.random.rand(3)
        self.opponent_features_vec = []

        models = [modeldir for modeldir in os.listdir(os.path.join(os.path.abspath(os.path.dirname(__file__)), "models")) if not modeldir.startswith('.')]
        for agent in models:
            model = SAC.load(os.path.join(os.path.abspath(os.path.dirname(__file__)), "models/{}/best_model.zip".format(agent)))
            with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), "models/{}/feature.npy".format(agent)), 'rb') as f:
                feature = np.load(f, allow_pickle=True)
            self.strategies.append(Strategy(model, agent, feature))
            self.centroids.append(feature)

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
            self.opponent_model = OpponentModel(self.domain)
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
            progress = self.progress.get(time() * 1000)
            if progress < 0.75:
                self.opponent_model.update(bid)
            # set bid as last received
            self.last_received_bid = bid if bid.getIssueValues() != dict() else None

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        if self._best is None:
            for bid in self.all_bids:
                if self._max < float(self.profile.getUtility(bid)):
                    self._max = float(self.profile.getUtility(bid))
                    self._best = bid
        if self.last_received_bid is not None:
            self.partner_offers.append(self.last_received_bid)
            self.partner_uoffers.append(float(self.profile.getUtility(self.last_received_bid)))
            self.partner_utils.append(float(self.opponent_model(self.last_received_bid)))
            self.current_opponent_feature = get_opponent_features(self, self.last_received_bid)
            self.opponent_features_vec.append(self.current_opponent_feature)
        # check if the last received offer is good enough
        if self.accept_condition(self.last_received_bid):
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            progress = self.progress.get(time() * 1000)
            bid = self.find_bid(self.last_received_bid, progress)
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

        offer_util = float(self.profile.getUtility(bid))
        self.profile.getUtilities()

        myoffer = self.find_bid(bid, progress, mode=ProposePurpose.TO_RESPOND)
        my_next_proposal_util = float(self.profile.getUtility(myoffer))
        if my_next_proposal_util is not None and offer_util * 1.1 >= my_next_proposal_util:
            return True
        if progress >= self._thr_time and offer_util > max(self.partner_uoffers) * 1.1:
            return True
        return False

    def find_bid(self, bid: Bid, progress: float, mode=ProposePurpose.TO_PROPOSE) -> Bid:
        if len(self.opponent_features_vec) == 0:
            pr = [1 / len(self.strategies)] * len(self.strategies)
        else:
            f_length = len(self.opponent_features_vec)
            if len(self.centroids[0]) < f_length:
                lower = max(len(self.centroids[0])-10, 0)
                upper = len(self.centroids[0])
            else:
                lower = max(f_length-10, 0)
                upper = f_length
            cos_sim = [np.sum(self.opponent_features_vec[lower:upper] * c[lower:upper], axis=-1) / (np.linalg.norm(self.opponent_features_vec[lower:upper], axis=-1) * np.linalg.norm(c[lower:upper], axis=-1)) for c in self.centroids]
            pr = [np.sum(c)+1e-9 for c in cos_sim]
            pr = [p / sum(pr) for p in pr]
        
        objective_util = self.switch_strategy(pr)

        if progress < self._thr_time:
            # # compose a list of all possible bids
            candidate_bids = []
            for b in self.all_bids:
                u = float(self.profile.getUtility(b))
                if u >= objective_util and u < objective_util + 0.01:
                    candidate_bids.append(b)
            if len(candidate_bids) == 0:
                best_bid = self._best
            else:
                best_bid = sorted(candidate_bids, key=lambda x: float(self.opponent_model(x)), reverse=True)[0]
        elif progress > 0.98:
            best_bid = sorted(self.partner_offers, key=lambda x: float(self.profile.getUtility(x)), reverse=True)[0]
        else:
            candidate_bids = []
            for b in self.all_bids:
                u = float(self.profile.getUtility(b))
                if u > objective_util - 0.05 and u < objective_util + 0.01:
                    candidate_bids.append(b)
            if len(candidate_bids) == 0:
                best_bid = self._best
            else:
                best_bid = sorted(candidate_bids, key=lambda x: float(self.opponent_model(x)), reverse=True)[0]

        if mode == ProposePurpose.TO_PROPOSE:
            self.uoffers.append(float(self.profile.getUtility(best_bid)))

        return best_bid
    
    def switch_strategy(self, pr):
        tr = self.progress.get(time() * 1000)
        _state = np.array([
            tr,
            self.uoffers[-3], self.partner_uoffers[-3],
            self.uoffers[-2], self.partner_uoffers[-2],
            self.uoffers[-1], self.partner_uoffers[-1],
        ])
        
        det_pr = self.stochastic_func(tr)
        deterministic = np.random.choice([False, True], p=[det_pr, 1-det_pr])
        if deterministic:
            strategy = self.strategies[np.argmax(pr)]
            return strategy(_state)
        else:
            strategy = np.random.choice(self.strategies, p=pr)
            return strategy(_state)
    
    def stochastic_func(self, x):
        return 1
        # if x < 0.3 or x > 0.7:
        #     return 0
        # else:
        #     return 1
