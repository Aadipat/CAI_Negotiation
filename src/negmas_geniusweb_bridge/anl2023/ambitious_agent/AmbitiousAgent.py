#######################################################
# author: Arash Ebrahimnezhad
# Email: Arash.ebrah@gmail.com
#######################################################
from typing import List
from geniusweb.issuevalue.Value import Value
from geniusweb.bidspace.IssueInfo import IssueInfo
from geniusweb.bidspace.Interval import Interval
from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from datetime import datetime
import logging
from random import randint
import random
from time import time
from tkinter.messagebox import NO
from typing import cast
import math
import pickle
import os
from statistics import mean
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
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from .utils.opponent_model import OpponentModel
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from decimal import Decimal
from geniusweb.opponentmodel import FrequencyOpponentModel


NUMBER_OF_GOALS = 5


class AmbitiousAgent(DefaultParty):
    """
    ANL 2023 AmbitiousAgent that learns over negotiation sessions.

    Uses epsilon-greedy algorithm for learning and adaptive bidding strategies.
    Supports ProgressTime protocol with time-based acceptance conditions.

    Note:
        This agent requires ProgressTime (not ProgressRounds) and uses getStart()
        method which may not be available in all wrappers. The agent is marked
        as having known issues when used with round-based protocols.
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

        self.received_bid_details = []
        self.my_bid_details = []
        self.best_received_bid = None

        self.logger.log(logging.INFO, "party is initialized")

        # self.pattern = randint(0, PATTERN_SIZE)
        self.agreement_utility = 0.0
        self._utilspace: LinearAdditive = None  # type:ignore
        self.who_accepted = None

        self.is_called = False

        # *************************************************
        # ****************** Parameters *******************
        # *************************************************
        # Initial Bidding Strategy parameters
        self.max = 1.0
        self.min = 0.6
        self.e = 0.05

        # Learning over Negotiation Sessions parameters
        self.increasing_e = 0.025
        self.decreasing_e = 0.025
        self.epsilon = 1.0
        self.good_agreement_u = 0.93
        self.condition_d = 0

        # Acceptance Strategy parameters
        self.near_deadline = 0.97
        self.alpha = 1.0
        self.betta = 0.0

        # *************************************************
        # **************** Parameters 2023 ****************
        # *************************************************
        # Acceptance Strategy parameters 2023

        # should be calculated considering the deadline and the opponent offering speed
        self.near_deadline_2023 = 0.99

        # number of time we negotiated agaist pricular opponent (Current number of parallel negotiation sessions)
        self.ns_repetation_2023 = 0

        self.max_num_ns_repetation_2023 = 49.0
        self.ac_e_2023 = 0.05
        self.ac_min_2023 = 0.4

        # calculate average time to recieve each offer from the opponent for last 10 offers
        self.avg_time_consumption = 0.00001  # time consumed for the opponent's offering
        self.time_consumption_list = []  # time_consumption list

        # average time_consumption to produce a bid by the opponent according previous ns
        self.avg_time_consumption_all_ns = 0

        self.t1 = 0
        self.t2 = 0
        self.alpha_ac_2023 = 1.0
        self.betta_ac_2023 = 0.0

        self.ratio = 0  # this value is used to tune the bidding strategy
        self.alpha_ratio = 2.0

        # is AC2023 returned True?
        self.is_ac2023 = 0
        # to investigation of AC2023 effect
        self.AC2023_effect = []

    def ff(self, ll, n):
        x_list = []
        for x in ll[::-1]:
            if x[1] == n:
                x_list.append(x[0])
            else:
                break
        if len(x_list) > 0:
            m = mean(x_list)
        else:
            m = 0.8
        return m

    # Alg2 (epsilon greedy)
    def Alg_2(self, saved_data, condition_data, opp):
        rand_num = random.random()
        if rand_num > self.epsilon:
            self.min = saved_data[opp][-1][1]
            self.e = saved_data[opp][-1][2]
        else:
            self.LSN(saved_data, condition_data, opp)

    # SLM (Stop Learning Mechanism)
    def SLM(self, saved_data, condition_data, opp):
        if (saved_data[opp][-2][0] == 0 and saved_data[opp][-1][0] > 0) or (
            (saved_data[opp][-2][1] == saved_data[opp][-1][1])
            and (saved_data[opp][-2][2] == saved_data[opp][-1][2])
        ):
            self.condition_d = condition_data[opp] + saved_data[opp][-1][0]
            if 0 <= self.condition_d < 1:
                self.condition_d = 1
            self.epsilon = self.epsilon / self.condition_d
            ###################### Alg 2 #####################
            self.Alg_2(saved_data, condition_data, opp)
            ##################################################
        else:
            self.LSN(saved_data, condition_data, opp)

    # LSN ( Learning over Negotiation Sessions = LNS )
    def LSN(self, saved_data, condition_data, opp):
        if (
            saved_data[opp][-1][0] > 0
            and saved_data[opp][-1][0] < self.good_agreement_u
        ):
            self.min = saved_data[opp][-1][1] + self.increasing_e
            self.e = saved_data[opp][-1][2] - self.increasing_e

        if saved_data[opp][-1][0] == 0:
            self.condition_d = condition_data[opp] - (
                1 - self.ff(saved_data[opp], saved_data[opp][-1][1])
            )
            if self.condition_d < 0:
                self.condition_d = 0
            self.min = saved_data[opp][-1][1] - self.decreasing_e
            self.e = saved_data[opp][-1][2] + self.decreasing_e

        if saved_data[opp][-1][0] >= self.good_agreement_u:
            self.min = saved_data[opp][-1][1]
            self.e = saved_data[opp][-1][2]

    def get_avg_all_list(self, DataList):
        num = 0
        m_sum = 0
        for dl in DataList[self.other]:
            num += len(dl)
            m_sum += sum(dl)
        return float(m_sum) / num

    # set parameters using LSN, SLM and Alg2
    def set_parameters(self, opp):
        # Calculate AVG time consumption according of all previous NS (2023)
        if not self.other or not os.path.exists(
            f"{self.storage_dir}/time_consumption_data_{self.other}"
        ):
            self.avg_time_consumption_all_ns = 0
        else:
            self.avg_time_consumption_all_ns = self.get_avg_all_list(
                self.return_saved_data(f"time_consumption_data_{self.other}")
            )
            if self.avg_time_consumption_all_ns > 0:
                self.ratio = (self.get_domain_size(self.domain)) / (
                    15000
                    * (
                        self.progress.getDuration()
                        / (self.avg_time_consumption_all_ns * 1000)
                    )
                )

        # If there is no negotiation exprience with opponent (opp) so set min=0.6 and e=0.05
        if not self.other or not os.path.exists(
            f"{self.storage_dir}/m_data_{self.other}"
        ):
            self.min = 0.6
            self.e = 0.05
        else:
            self.AC2023_effect = self.return_saved_data(f"AC2023_data_{self.other}")
            saved_data = self.return_saved_data(f"m_data_{self.other}")
            condition_data = self.return_saved_data(f"c_data_{self.other}")
            if (saved_data is not None) and (condition_data is not None):
                if opp in saved_data:
                    self.good_agreement_u = self.good_agreement_u - (
                        len(saved_data[opp]) * 0.01
                    )
                    if self.good_agreement_u < 0.7:
                        self.good_agreement_u = 0.7
                    if len(saved_data[opp]) >= 2:
                        # SLM (Stop Learning Mechanism)
                        self.SLM(saved_data, condition_data, opp)
                    else:
                        self.LSN(saved_data, condition_data, opp)
                else:
                    self.min = 0.6
                    self.e = 0.05
            else:
                self.min = 0.6
                self.e = 0.05

        # Make correction
        if self.min < 0.5:
            self.min = 0.5
        if self.min > 0.7:
            self.min = 0.7

        # Tune e using Ratio
        self.e += self.ratio / self.alpha_ratio

        if self.e < 0.005:
            self.e = 0.005
        if self.e > 0.1:
            self.e = 0.1

        # Tune max using Ratio
        self.max -= self.alpha_ratio * self.ratio
        if self.max <= self.min:
            self.max = self.min + 0.001

    def return_saved_data(self, file_name):
        # for reading also binary mode is important
        if os.path.exists(f"{self.storage_dir}/{file_name}"):
            file = open(f"{self.storage_dir}/{file_name}", "rb")
            saved_data = pickle.load(file)
            file.close()
            return saved_data
        return None

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

            # **************************** 2023 ****************************
            ns_repetation_2023_domain = 0
            try:
                ns_repetation_2023_domain = int(self.domain.getName()[-2:])
            except:
                ns_repetation_2023_domain = 0

            ns_repetation_2023_saved_data = 0
            if self.other is not None:
                ns_repetation_2023_saved_data = len(
                    self.return_saved_data((f"m_data_{self.other}"))[self.other]
                )
            else:
                ns_repetation_2023_saved_data = None

            # This peace of code check whether domain number is equal to saved data length or not
            if ns_repetation_2023_saved_data is not None:
                if ns_repetation_2023_saved_data == ns_repetation_2023_domain:
                    self.ns_repetation_2023 = ns_repetation_2023_domain
                elif (
                    ns_repetation_2023_domain > ns_repetation_2023_saved_data
                    and abs(ns_repetation_2023_domain - ns_repetation_2023_saved_data)
                    <= 4
                ):
                    self.ns_repetation_2023 = ns_repetation_2023_domain
                elif (
                    ns_repetation_2023_domain > ns_repetation_2023_saved_data
                    and abs(ns_repetation_2023_domain - ns_repetation_2023_saved_data)
                    > 4
                ):
                    self.ns_repetation_2023 = ns_repetation_2023_saved_data
                elif ns_repetation_2023_domain < ns_repetation_2023_saved_data:
                    self.ns_repetation_2023 = ns_repetation_2023_saved_data
            else:
                self.ns_repetation_2023 = 0

            if self.ns_repetation_2023 > 49:
                self.ns_repetation_2023 = 49
            if self.ns_repetation_2023 < 0:
                self.ns_repetation_2023 = 0
            # **************************************************************

            # initialize FrequencyOpponentModel
            self.opponent_model = (
                FrequencyOpponentModel.FrequencyOpponentModel.create().With(
                    newDomain=self.profile.getDomain(),
                    newResBid=self.profile.getReservationBid(),
                )
            )

            profile_connection.close()

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()

            actor = action.getActor()

            if isinstance(action, Accept):
                # print(str(actor).rsplit("_", 1)[0], '=>', cast(Offer, action).getBid())
                agreement_bid = cast(Offer, action).getBid()
                self.agreement_utility = float(self.profile.getUtility(agreement_bid))
                self.who_accepted = str(actor).rsplit("_", 1)[0]

            # ignore action if it is our action
            if actor != self.me:
                # obtain the name of the opponent, cutting of the position ID.
                self.other = str(actor).rsplit("_", 1)[0]

                # set parameters according of saved data
                if not self.is_called:
                    self.set_parameters(self.other)
                    self.is_called = True

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

    def opponent_action(self, action):
        """Process an action that was received from the opponent.
        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):
            bid = cast(Offer, action).getBid()

            # update opponent model with bid
            self.opponent_model = self.opponent_model.WithAction(
                action=action, progress=self.progress
            )
            # set bid as last received
            self.last_received_bid = bid
            # self.received_bids.append(bid)
            self.received_bid_details.append(
                BidDetail(
                    bid,
                    float(self.profile.getUtility(bid)),
                    self.progress.get(time() * 1000),
                )
            )

            if self.best_received_bid is None:
                self.best_received_bid = BidDetail(
                    bid, float(self.profile.getUtility(self.last_received_bid))
                )
            elif (
                float(self.profile.getUtility(self.last_received_bid))
                > self.best_received_bid.getUtility()
            ):
                self.best_received_bid = BidDetail(
                    self.last_received_bid,
                    float(self.profile.getUtility(self.last_received_bid)),
                )

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        # **************************** 2023 ****************************
        if self.t1 == 0:
            self.t1 = time()
        elif self.t2 == 0:
            self.t2 = time()

        if self.t1 != 0 and self.t2 != 0 and self.t2 > self.t1:
            self.time_consumption_list.append(self.t2 - self.t1)
            self.t1 = self.t2
            self.t2 = 0

        self.cal_thresholds()
        # **************************************************************

        # **************************** 2023 ****************************
        avg_offer_time = 0
        remaining_time = 0

        remaining_time = (
            time() - float(datetime.timestamp(self.progress.getStart()))
        ) * 1000

        # calculate opponent average offering time (current NS)
        if len(self.time_consumption_list) > 0:
            avg_offer_time = (
                sum(self.time_consumption_list) / len(self.time_consumption_list)
            ) * 1000

        # investigate if the time passed of the negotiation session is near to deadline
        if (
            remaining_time + (self.alpha_ac_2023 * avg_offer_time + self.betta_ac_2023)
            > self.progress.getDuration()
        ):
            if self.accept_condition_2023(self.last_received_bid):
                self.send_action(Accept(self.me, self.last_received_bid))
            else:
                self._updateUtilSpace()
                next_bid = self.find_bid()
                # check if the last received offer is good enough
                if self.accept_condition(self.last_received_bid, next_bid):
                    # if so, accept the offer
                    action = Accept(self.me, self.last_received_bid)
                    # send the action
                    self.send_action(action)
                else:
                    # if not, send the best bid that we received ever
                    if self.accept_condition_2023(self.best_received_bid.getBid()):
                        action = Offer(self.me, self.best_received_bid.getBid())
                        # self.my_bids.append(next_bid)
                        self.my_bid_details.append(self.best_received_bid)

                        # send the action
                        self.send_action(action)
                    else:
                        action = Offer(self.me, next_bid)
                        self.send_action(action)
        else:
            # **************************************************************

            self._updateUtilSpace()

            next_bid = self.find_bid()
            # check if the last received offer is good enough
            if self.accept_condition(self.last_received_bid, next_bid):
                # if so, accept the offer
                action = Accept(self.me, self.last_received_bid)
            else:
                # if not, find a bid to propose as counter offer
                action = Offer(self.me, next_bid)
                # self.my_bids.append(next_bid)
                self.my_bid_details.append(
                    BidDetail(next_bid, float(self.profile.getUtility(next_bid)))
                )

            # send the action
            self.send_action(action)

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        # **************************************************
        if self.other:
            c_file_name = "c_data_" + self.other
            c_data = {}
            if os.path.isfile(f"{self.storage_dir}/{c_file_name}"):
                dbfile_c = open(f"{self.storage_dir}/{c_file_name}", "rb")
                c_data = pickle.load(dbfile_c)
                dbfile_c.close()

            if os.path.exists(f"{self.storage_dir}/{c_file_name}"):
                os.remove(f"{self.storage_dir}/{c_file_name}")

            c_data[self.other] = self.condition_d
            dbfile_c = open(f"{self.storage_dir}/{c_file_name}", "ab")
            pickle.dump(c_data, dbfile_c)
            dbfile_c.close()

            m_file_name = "m_data_" + self.other
            m_data = {}
            if os.path.isfile(f"{self.storage_dir}/{m_file_name}"):
                dbfile = open(f"{self.storage_dir}/{m_file_name}", "rb")
                m_data = pickle.load(dbfile)
                dbfile.close()

            if os.path.exists(f"{self.storage_dir}/{m_file_name}"):
                os.remove(f"{self.storage_dir}/{m_file_name}")

            m_tuple = (self.agreement_utility, self.min, self.e)
            if self.other in m_data:
                m_data[self.other].append(m_tuple)
            else:
                m_data[self.other] = [
                    m_tuple,
                ]

            dbfile = open(f"{self.storage_dir}/{m_file_name}", "ab")

            # source, destination
            pickle.dump(m_data, dbfile)
            dbfile.close()

            # ////////////////////////////////////////////////////////////////////////
            # ////////////////////// Save AVG time consumption ///////////////////////
            # ////////////////////////////////////////////////////////////////////////
            if len(self.time_consumption_list) == 0:
                self.time_consumption_list.append(self.progress.getDuration() / 1000.0)
            time_consumption2023_file_name = f"time_consumption_data_{self.other}"
            time_consumption2023_data = {}
            if os.path.isfile(f"{self.storage_dir}/{time_consumption2023_file_name}"):
                dbfile = open(
                    f"{self.storage_dir}/{time_consumption2023_file_name}", "rb"
                )
                time_consumption2023_data = pickle.load(dbfile)
                dbfile.close()

            if os.path.exists(f"{self.storage_dir}/{time_consumption2023_file_name}"):
                os.remove(f"{self.storage_dir}/{time_consumption2023_file_name}")

            if self.other in time_consumption2023_data:
                time_consumption2023_data[self.other].append(self.time_consumption_list)
            else:
                time_consumption2023_data[self.other] = [
                    self.time_consumption_list,
                ]

            dbfile = open(f"{self.storage_dir}/{time_consumption2023_file_name}", "ab")

            # source, destination
            pickle.dump(time_consumption2023_data, dbfile)
            dbfile.close()

    def accept_condition(self, received_bid: Bid, next_bid) -> bool:
        if received_bid is None:
            return False

        progress = self.progress.get(time() * 1000)

        # set reservation value
        if self.profile.getReservationBid() is None:
            reservation = 0.0
        else:
            reservation = self.profile.getUtility(self.profile.getReservationBid())

        received_bid_utility = self.profile.getUtility(received_bid)
        condition1 = (
            received_bid_utility >= self.threshold_acceptance
            and received_bid_utility >= reservation
        )
        condition2 = (
            progress > self.near_deadline
            and received_bid_utility > self.min
            and received_bid_utility >= reservation
        )
        condition3 = (
            self.alpha * float(received_bid_utility) + self.betta
            >= float(self.profile.getUtility(next_bid))
            and received_bid_utility >= reservation
        )

        return condition1 or condition2 or condition3

    def find_bid(self) -> Bid:
        """
        @return next possible bid with current target utility, or null if no such
                bid.
        """
        interval = self.threshold_high - self.threshold_low
        s = interval / NUMBER_OF_GOALS

        utility_goals = []
        for i in range(NUMBER_OF_GOALS):
            utility_goals.append(self.threshold_low + s * i)
        utility_goals.append(self.threshold_high)

        options: ImmutableList[Bid] = self._extendedspace.getBids(
            Decimal(random.choice(utility_goals))
        )

        opponent_utilities = []
        for option in options:
            if self.opponent_model != None:
                opp_utility = float(self.opponent_model.getUtility(option))
                if opp_utility > 0:
                    opponent_utilities.append(opp_utility)
                else:
                    opponent_utilities.append(0.00001)
            else:
                opponent_utilities.append(0.00001)

        if options.size() == 0:
            # if we can't find good bid, get max util bid....
            options = self._extendedspace.getBids(self._extendedspace.getMax())
            return options.get(randint(0, options.size() - 1))
        # pick a random one.

        next_bid = random.choices(list(options), weights=opponent_utilities)[0]
        for bid_detaile in self.received_bid_details:
            if bid_detaile.getUtility() >= self.profile.getUtility(next_bid):
                next_bid = bid_detaile.getBid()

        return random.choices(list(options), weights=opponent_utilities)[0]

    # ************************************************************
    def f(self, t, k, e):
        return k + (1 - k) * (t ** (1 / e))

    def p(self, min1, max1, e, t):
        return min1 + (1 - self.f(t, 0, e)) * (max1 - min1)

    def cal_thresholds(self):
        progress = self.progress.get(time() * 1000)
        self.threshold_high = self.p(self.min + 0.1, self.max, self.e, progress)
        self.threshold_acceptance = self.p(
            self.min + 0.1, self.max, self.e, progress
        ) - (0.1 * (progress + 0.0000001))
        self.threshold_low = self.p(self.min + 0.1, self.max, self.e, progress) - (
            0.1 * (progress + 0.0000001)
        ) * abs(math.sin(progress * 60))

    # ================================================================
    def get_domain_size(self, domain: Domain):
        domain_size = 1
        for issue in domain.getIssues():
            domain_size *= domain.getValues(issue).size()
        return domain_size

    # ================================================================

    # give a description of your agent
    def getDescription(self) -> str:
        """MUST BE IMPLEMENTED
        Returns a description of your agent. 1 or 2 sentences.
        Returns:
            str: Agent description
        """
        return "AmbitiousAgent"

    def send_action(self, action: Action):
        """Sends an action to the opponent(s)
        Args:
            action (Action): action of this agent
        """
        self.getConnection().send(action)

    def _updateUtilSpace(self) -> LinearAdditive:  # throws IOException
        newutilspace = self.profile
        if not newutilspace == self._utilspace:
            self._utilspace = cast(LinearAdditive, newutilspace)
            self._extendedspace = ExtendedUtilSpace(self._utilspace)
        return self._utilspace

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

    ###########################################################################################
    ######################################### 2023 Codes ######################################
    ###########################################################################################
    def accept_condition_2023(self, received_bid):
        if received_bid is None:
            return False

        # set reservation value
        if self.profile.getReservationBid() is None:
            reservation = 0.0
        else:
            reservation = self.profile.getUtility(self.profile.getReservationBid())

        p = self.p(
            self.ac_min_2023,
            self.min,
            self.ac_e_2023,
            float(self.ns_repetation_2023 / self.max_num_ns_repetation_2023),
        )

        recieved_bid_u = self.profile.getUtility(received_bid)

        if recieved_bid_u >= p and recieved_bid_u >= reservation:
            self.is_ac2023 = float(recieved_bid_u)
        else:
            self.is_ac2023 = 0

        return recieved_bid_u >= p and recieved_bid_u >= reservation


class BidDetail:
    def __init__(self, bid: Bid, utility: float, time: float = None):
        self.__bid = bid
        self.__utiltiy = utility
        self.__time = time

    def getBid(self):
        return self.__bid

    def getUtility(self):
        return self.__utiltiy

    def getTime(self):
        return self.__time

    def __repr__(self) -> str:
        return f"{self.__bid}: {self.__utiltiy}"


class ExtendedUtilSpace:
    """
    Inner class for TimeDependentParty, made public for testing purposes. This
    class may change in the future, use at your own risk.
    """

    def __init__(self, space: LinearAdditive):
        self._utilspace = space
        self._bidutils = BidsWithUtility.create(self._utilspace)
        self._computeMinMax()
        self._tolerance = self._computeTolerance()

    def _computeMinMax(self):
        """
        Computes the fields minutil and maxUtil.
        <p>
        TODO this is simplistic, very expensive method and may cause us to run
        out of time on large domains.
        <p>
        Assumes that utilspace and bidutils have been set properly.
        """
        range = self._bidutils.getRange()
        self._minUtil = range.getMin()
        self._maxUtil = range.getMax()

        rvbid = self._utilspace.getReservationBid()
        if rvbid != None:
            rv = self._utilspace.getUtility(rvbid)
            if rv > self._minUtil:
                self._minUtil = rv

    def _computeTolerance(self) -> Decimal:
        """
        Tolerance is the Interval we need when searching bids. When we are close
        to the maximum utility, this value has to be the distance between the
        best and one-but-best utility.

        @return the minimum tolerance required, which is the minimum difference
                between the weighted utility of the best and one-but-best issue
                value.
        """
        tolerance = Decimal(1)
        for iss in self._bidutils.getInfo():
            if iss.getValues().size() > 1:
                # we have at least 2 values.
                values: List[Decimal] = []
                for val in iss.getValues():
                    values.append(iss.getWeightedUtil(val))
                values.sort()
                values.reverse()
                tolerance = min(tolerance, values[0] - values[1])
        return tolerance

    def getMin(self) -> Decimal:
        return self._minUtil

    def getMax(self) -> Decimal:
        return self._maxUtil

    def getBids(self, utilityGoal: Decimal) -> ImmutableList[Bid]:
        """
        @param utilityGoal the requested utility
        @return bids with utility inside [utilitygoal-{@link #tolerance},
                utilitygoal]
        """
        return self._bidutils.getBids(
            Interval(utilityGoal - self._tolerance, utilityGoal)
        )
