import json
import logging
import time
from os import path
from random import randint
from typing import cast, TypedDict

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


class SessionData(TypedDict):
    numberOfAgreement: int
    roundsAtFinish: int
    numberOfLastBids: int
    usingStep: int
    numberOfTimes: int
    lastAgreement: int


class DataDict(TypedDict):
    sessions: list[SessionData]


class AntHeartAgent(DefaultParty):
    """
    Implementation of the MiCRO strategy for ANAC 2022. MiCRO is a very simple strategy that just proposes all possible bids of the domain one by one, in order of decreasing utility, as long as the opponent keeps making new proposals as well.
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
        self.allMyBidsSorted: list = None
        self.receivedBids = set()
        self.microIndex = 0
        self.reservationValue = 0

        self.timeToConcede = 0.9
        self.myLastBid: Bid = None
        self.roundsCount = 0
        self.lastReceivedBids = set()
        self.bidIndexList: list = None
        self.macroIndex = 0
        self.useMicro = 0
        self.useMacro = 0
        self.macroStep = 10
        self.microStep = 1
        self.data_dict: DataDict = None
        self.numberOfAgreement: int = 0
        self.roundsAtFinish: int = 0
        self.numberOfLastBids: int = 0
        self.usingStep: int = 0
        self.numberOfTimes = 0
        self.Agreement = 0

        self.opponent_model: OpponentModel = None

        self.logger.log(logging.INFO, "party is initialized")

    def notifyChange(self, data: Inform):
        """MUST BE IMPLEMENTED
        This is the entry point of all interaction with your agent after is has been initialised.
        How to handle the received data is based on its class type.

        Args:
            info (Inform): Contains either a request for action or information.
        """
        if isinstance(data, Settings):
            self.settings = cast(Settings, data)
            self.me = self.settings.getID()

            self.progress = self.settings.getProgress()

            self.parameters = self.settings.getParameters()
            self.storage_dir = self.parameters.get("storage_dir")

            profile_connection = ProfileConnectionFactory.create(
                data.getProfile().getURI(), self.getReporter()
            )
            self.profile = profile_connection.getProfile()
            self.domain = self.profile.getDomain()
            profile_connection.close()

            domain = self.profile.getDomain()
            all_bids = AllBidsList(domain)
            self.allMyBidsSorted = list(all_bids)
            self.allMyBidsSorted.sort(reverse=True, key=self.profile.getUtility)

        elif isinstance(data, ActionDone):

            action = cast(ActionDone, data).getAction()
            actor = action.getActor()

            # ignore action if it is our action
            if actor != self.me:
                # obtain the name of the opponent, cutting of the position ID.
                self.other = str(actor).rsplit("_", 1)[0]
                self.attempt_load_data()
                self.generate_MaCRO_step()

                # process action done by opponent
                self.opponent_action(action)

        elif isinstance(data, YourTurn):
            # execute a turn
            self.my_turn()

        elif isinstance(data, Finished):
            self.update_data_dict()
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
        return "ANAC 2023 MyAgent"

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        if isinstance(action, Accept):
            self.numberOfAgreement += 1
            self.Agreement = 1

        if isinstance(action, Offer):
            if self.opponent_model is None:
                self.opponent_model = OpponentModel(self.domain)

            bid = cast(Offer, action).getBid()
            self.opponent_model.update(bid)

            # set bid as last received
            self.last_received_bid = bid

            # add bid to set of all received bids.
            self.receivedBids.add(bid)

            progress = self.progress.get(time.time() * 1000)
            if progress > self.timeToConcede:
                self.lastReceivedBids.add(bid)

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        progress = self.progress.get(time.time() * 1000)

        self.roundsCount += 1

        if self.opponent_model is None:
            self.opponent_model = OpponentModel(self.domain)

        if progress <= self.timeToConcede:
            self.get_MiCRO_bid()
        else:
            if len(self.allMyBidsSorted) > 30:
                self.get_MaCRO_bid()
            else:
                self.get_MiCRO_bid()

    def acceptanceStrategy(self, readyToConcede: bool) -> bool:

        utilityOfLastReceivedOffer = self.profile.getUtility(self.last_received_bid)

        if utilityOfLastReceivedOffer <= self.reservationValue:
            return False

        if readyToConcede:
            lowestAcceptableBid = self.allMyBidsSorted[self.microIndex]
        else:
            lowestAcceptableBid = self.allMyBidsSorted[self.microIndex - self.microStep]

        lowestAcceptableUtility = self.profile.getUtility(lowestAcceptableBid)

        return utilityOfLastReceivedOffer >= lowestAcceptableUtility

    def acceptanceStrategy_2(self, readyToConcede_2: bool) -> bool:
        utilityOfLastReceivedOffer = self.profile.getUtility(self.last_received_bid)

        if utilityOfLastReceivedOffer <= self.reservationValue:
            return False

        if readyToConcede_2:
            lowestAcceptableBid = self.allMyBidsSorted[self.macroIndex]
        else:
            lowestAcceptableBid = self.allMyBidsSorted[self.macroIndex - self.macroStep]

        lowestAcceptableUtility = self.profile.getUtility(lowestAcceptableBid)

        return utilityOfLastReceivedOffer >= lowestAcceptableUtility

    def get_data_file_path(self) -> str:
        return f"{self.storage_dir}/{self.other}.json"

    def attempt_load_data(self):
        if path.exists(self.get_data_file_path()):
            with open(self.get_data_file_path()) as f:
                self.data_dict = json.load(f)
                sessions = self.data_dict["sessions"]

                self.numberOfAgreement = sessions[0]["numberOfAgreement"]
                self.roundsAtFinish = sessions[0]["roundsAtFinish"]
                self.numberOfLastBids = sessions[0]["numberOfLastBids"]
                self.usingStep = sessions[0]["usingStep"]
                self.numberOfTimes = sessions[0]["numberOfTimes"]
                self.lastAgreement = sessions[0]["lastAgreement"]
                self.macroStep = self.usingStep

        else:
            # initialize an empty data dict
            self.data_dict = {
                "sessions": [
                    {
                        "numberOfAgreement": 0,
                        "numberOfLastBids": 0,
                        "roundsAtFinish": 0,
                        "usingStep": 0,
                        "numberOfTimes": 0,
                        "lastAgreement": 0
                    }
                ]
            }

    def update_data_dict(self):
        self.data_dict = {
            "sessions": [
                {
                    "numberOfAgreement": self.numberOfAgreement,
                    "numberOfLastBids": (self.numberOfLastBids * self.numberOfTimes + len(self.lastReceivedBids)) / (
                            self.numberOfTimes + 1),
                    "roundsAtFinish": (self.roundsAtFinish * self.numberOfTimes + self.roundsCount * 2) / (
                            self.numberOfTimes + 1),
                    "usingStep": self.macroStep,
                    "numberOfTimes": self.numberOfTimes + 1,
                    "lastAgreement": self.Agreement
                }
            ]
        }

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        if self.other is None:
            self.logger.log(logging.WARNING, "Opponent name was not set; skipping save data")
        else:
            json_data = json.dumps(self.data_dict, sort_keys=True, indent=4)
            with open(self.get_data_file_path(), "w") as f:
                f.write(json_data)

    def generate_MiCRO_step(self):
        max_utility = 0
        for i in range(self.microIndex + 1, self.microIndex + 3):
            bid = self.allMyBidsSorted[i]
            utility = self.opponent_model.get_predicted_utility(bid)
            if utility > max_utility:
                max_utility = utility
                self.microStep = i - self.microIndex

    def generate_MaCRO_step(self):
        if self.numberOfTimes > 10:
            if self.lastAgreement == 0:
                if (self.numberOfAgreement / self.numberOfTimes) < 0.75:
                    if self.numberOfLastBids < 50:
                        self.macroStep += 5
                    else:
                        self.macroStep += 3
                    self.macroStep = min(self.macroStep, 20)

    def get_MiCRO_bid(self) -> Bid:
        if self.useMicro == 0:
            self.useMicro = 1
            self.bidIndexList = []

        readyToConcede = False

        if self.bidIndexList is not None:
            readyToConcede = len(self.bidIndexList) <= len(self.receivedBids)

        if self.last_received_bid is not None:
            accept = self.acceptanceStrategy(readyToConcede)
            if accept:
                action = Accept(self.me, self.last_received_bid)
                self.numberOfAgreement += 1
                self.Agreement = 1
                self.send_action(action)
                return

        myNextBid = self.allMyBidsSorted[self.microIndex]

        if readyToConcede and self.profile.getUtility(myNextBid) > self.reservationValue:
            self.bidIndexList.append(self.microIndex)

            progress = self.progress.get(time.time() * 1000)
            if progress < 0.5:
                self.microStep = 1
            else:
                if len(self.allMyBidsSorted) > 30:
                    self.generate_MiCRO_step()
            self.microIndex += self.microStep

            action = Offer(self.me, myNextBid)
            self.myLastBid = myNextBid
            self.send_action(action)
            return
        else:
            if self.bidIndexList is None:
                randomBid = self.allMyBidsSorted[0]
            else:
                randomIndex = randint(0, len(self.bidIndexList) - 1)
                randomBid = self.allMyBidsSorted[self.bidIndexList[randomIndex]]
            action = Offer(self.me, randomBid)
            self.myLastBid = randomBid
            self.send_action(action)
            return

    def get_MaCRO_bid(self) -> Bid:
        if self.useMacro == 0:
            self.useMacro = 1
            self.macroIndex = self.microIndex + self.macroStep

        readyToConcede_2 = False

        if self.bidIndexList is not None:
            readyToConcede_2 = len(self.bidIndexList) <= len(self.receivedBids)

        if self.last_received_bid != None:
            accept = self.acceptanceStrategy_2(readyToConcede_2)
            if accept:
                action = Accept(self.me, self.last_received_bid)
                self.numberOfAgreement += 1
                self.Agreement = 1
                self.send_action(action)
                return

        myNextBid_2 = self.allMyBidsSorted[self.macroIndex]

        if readyToConcede_2 and self.profile.getUtility(myNextBid_2) > self.reservationValue:
            self.bidIndexList.append(self.macroIndex)
            self.macroIndex += self.macroStep
            action = Offer(self.me, myNextBid_2)
            self.myLastBid = myNextBid_2
            self.send_action(action)
            return
        else:
            if self.bidIndexList is None:
                randomBid = self.allMyBidsSorted[0]
            else:
                randomIndex = randint(0, len(self.bidIndexList) - 1)
                randomBid = self.allMyBidsSorted[self.bidIndexList[randomIndex]]
            action = Offer(self.me, randomBid)
            self.myLastBid = randomBid
            self.send_action(action)
            return
