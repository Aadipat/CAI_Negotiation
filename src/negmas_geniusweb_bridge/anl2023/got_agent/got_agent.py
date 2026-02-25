import logging
from random import randint
from time import time
from typing import cast
import numpy as np
import random
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

from .utils.genetic_algorithm import GeneticAlgorithm
from .utils.opponent_model import OpponentModel


class GotAgent(DefaultParty):
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
        self.other: str = None #name of the opponent
        self.settings: Settings = None
        self.storage_dir: str = None
        self.timeStr = None

        self.last_received_bid: Bid = None
        self.opponent_model: OpponentModel = None
        self.logger.log(logging.INFO, "party is initialized")

        self.processed_domain = False #have we processed the domain we're in? For both me and the opponent
        self.processed_IssuesValues = None #The structure of this dictionary is explained under method initialize_my domain
        self.namesNumbersDict = None
        self.start_bid_given = False
        self.perfect_bid = None #perfect for me
        self.progressPercentage = float(0)

        self.den=0
        self.ga=None
        self.guessed_utility_for_us = []

        self.max_op_util = None # Highest utility offer the opponent has sent yet
        self.reservation_value = 0.6 # minimum required utility to accept

        self.behaviour_window = 30

    def update_progress(self): # progress of the negotiation session between 0 and 1 (1 is deadline)
        self.progressPercentage = self.progress.get(time() * 1000)

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
            self.timeStr = self.parameters.get("timestr")

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
            self.update_progress()
            self.my_turn()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            # terminate the agent MUST BE CALLED
            # print("OPPONENT NAME", self.other)
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
    def getDescription(self) -> str: #TODO
        """MUST BE IMPLEMENTED
        Returns a description of your agent. 1 or 2 sentences.

        Returns:
            str: Agent description
        """
        return "Peace agent for the ANL 2023 competition"

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):
            # create opponent model if it was not yet initialised
            if self.opponent_model is None and not self.processed_domain: #this is if opponent started first
                self.initialize_domains_for_both()
                self.processed_domain = True
            bid = cast(Offer, action).getBid()
            # update opponent model with bid
            #if np.isclose(self.progress, 0.3, atol=0.01, rtol=0):
            self.opponent_model.update(bid, timeprogress=self.progressPercentage, update_opponent_metrics=True) #maybe we can do it only sometimes later
            if (self.opponent_model.numBids > (self.opponent_model.windowSize+1)*2 and self.opponent_model.numBids%2==0):
                #self.model_behaviour()
                self.ga.change_typ(self.decide_behaviour())
            # set bid as last received
            self.last_received_bid = bid
            self.ga.edit_all_weights(self.opponent_model.namesNumbersDict, self.opponent_model.issue_weights_this, self.opponent_model.value_weights)
            self.guessed_utility_for_us.append(self.ga.calculate_my_utility(self.ga.bid_to_bid(bid)))

            self.ga.add_opponent_bid(bid)
    

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        if self.opponent_model is None and not self.processed_domain: # we are also the starting party so initialize things
            self.initialize_domains_for_both()
            self.processed_domain = True
            action = Offer(self.me, self.perfect_bid)
        else:
            next_bid = self.find_bid() 
            if not self.max_op_util: # When this is the first opponent offer so no max val has been set
                self.max_op_util = self.profile.getUtility(self.last_received_bid)
            # update maximum opponent utility 
            self.max_op_util = max(self.max_op_util, self.profile.getUtility(self.last_received_bid))

            if (self.accept_condition(next_bid, self.last_received_bid)):
                action = Accept(self.me, self.last_received_bid)
            else:
                action = Offer(self.me, next_bid)

        # send the action
        self.send_action(action)

    def save_data(self):
        pass #not in use anymore, omitted

    ###########################################################################################
    ###########################################################################################

    def find_random_bids(self, abovethreshold):
        domain = self.profile.getDomain()
        all_bids = AllBidsList(domain)
        bid_to_send = None
        # take 200 attempts to find a bid according to a heuristic score
        for i in range(400):
            bid = all_bids.get(randint(0, all_bids.size() - 1))
            bid_score = self.score_bid(bid)
            if bid_score > abovethreshold:
                bid_to_send = bid
                break
            elif (i==399): bid_to_send = self.perfect_bid #ends up randomly sending the perfect bid if one isn't sent before
        return bid_to_send


    def accept_condition(self, our_bid: Bid, opp_bid: Bid) -> bool:
        if opp_bid is None:
            return False
        else:
            # adapted from Acceptance Conditions in Automated Negotiation
            opp_bid_util = self.profile.getUtility(opp_bid)
            # Reject all bids that are below our reservation value
            if opp_bid_util < self.reservation_value:
                return False
            our_bid_util = self.profile.getUtility(our_bid)
            
            # Check if last offer is better than the one we are about to send
            return our_bid_util <= opp_bid_util
            # else if we are in the last 10%, check if this is the best offer the opponent has given thus far


    def initialize_my_domain(self):
        '''
        the outermost dictionary has keys "issueA", "issueB" etc. as String, inside each value of these keys an example is shown below
        {
            "issueA" : {
                "myWeight" : 0.456574, #for ex.
                "opponentWeight": 0.3425276, #-> guessed ofc and sometimes updated -> also added later since at first we are not using it
                "numValues" : 3,
                "opponent_matrix_row": 0,
                "values": { # -> this is a dictionary of values
                            "valueA" : { # a third nested dictionary, my god this assignment, to calculate overall weight you can multiply issueWeight x valueWeight
                                    "myValueWeight" : 0.006,
                                    "opponentValueWeight": 0.074,
                                    "opponent_matrix_position": (0,0), #-> the tuple showing the position in opponent count matrix
                                },

                }
            "issueB" : {
             .....
            }
        }
        '''
        self.namesNumbersDict = dict()
        self.processed_IssuesValues = dict()
        the_very_best_bid_dict = dict()
        issues = self.profile._issueWeights #returns issuesvalues.keys()
        num_rows = 0 #for initializing opponent matrix, for issues
        num_columns_for_each_issue = []
        for issue in issues:
            num_columns = 0 #also for opponent matrix but for values
            max_var_value = -1
            max_var = None
            self.namesNumbersDict[str(issue)] = dict()
            self.namesNumbersDict[num_rows] = dict()
            self.processed_IssuesValues[str(issue)] = dict()
            self.processed_IssuesValues[str(issue)]["myWeight"] = float(self.profile.getWeight(issue))
            self.processed_IssuesValues[str(issue)]["opponent_matrix_row"] = num_rows
            variables = self.profile._issueUtilities[issue]._valueUtilities
            self.processed_IssuesValues[str(issue)]["numValues"] = len(variables)
            self.processed_IssuesValues[str(issue)]["values"] = dict()
            for variable in variables.keys():
                value = variables.get(variable)
                self.processed_IssuesValues[str(issue)]["values"][str(variable)[1:-1]] = dict()
                self.processed_IssuesValues[str(issue)]["values"][str(variable)[1:-1]]["myValueWeight"] = value
                self.processed_IssuesValues[str(issue)]["values"][str(variable)[1:-1]]["opponent_matrix_position"] = [num_rows, num_columns]
                self.namesNumbersDict[str(issue)][str(variable)[1:-1]] = [num_rows, num_columns]
                self.namesNumbersDict[num_rows][num_columns] = str((str(issue), str(variable)[1:-1]))
                num_columns = num_columns + 1
                if value > max_var_value:
                    max_var = variable
                    max_var_value = variables.get(variable)
            self.namesNumbersDict[str(issue)]["issueNo"] = num_rows
            num_rows = num_rows + 1
            num_columns_for_each_issue.append(num_columns)
            the_very_best_bid_dict[issue]=max_var

        self.perfect_bid = Bid(the_very_best_bid_dict)
        self.ga = GeneticAlgorithm(2,0,15,self.domain.getIssues(), self.domain.getIssuesValues(), self.profile.getWeights(), self.profile.getUtilities())

        return num_rows, num_columns_for_each_issue
         #print("BEST BID=")
        #for issue in the_very_best_bid_dict.keys():
        #    print(issue, "->", the_very_best_bid_dict.get(issue))


    def initialize_domains_for_both(self):
        # us
        num_rows, num_columns_for_each_issue = self.initialize_my_domain()
        # opponent
        self.opponent_model = OpponentModel(self.domain, num_rows, num_columns_for_each_issue, self.namesNumbersDict)
        # if we will save data also initialize that -> omitted



    def find_bid(self) -> Bid:
        if (not self.start_bid_given):
            self.start_bid_given=True
            #self.ga.estimated_utilities_per_round.append(self.ga.bid_to_bid(self.perfect_bid))
            self.ga.estimated_utilities_per_round.append(None)

            return self.perfect_bid
        else:
            self.ga.change_process_percentage(self.progressPercentage)
            return self.ga.find_bid()

    def score_bid(self, bid: Bid, alpha: float = 0.95, eps: float = 0.1) -> float: #rn we dont follow a time based strategy
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

        our_utility = float(self.profile.getUtility(bid))
       
        return our_utility

    # =====================================================================================================================
    # ===========================    BEHAVIOUR MODELLING - NOT IN USE ANYMORE/OMMITTED     ================================
    # =====================================================================================================================
    
#    def model_behaviour(self):
#        lately = self.guessed_utility_for_us[-self.behaviour_window:]
#        a_2, b_2 = np.polyfit(np.arange(len(lately)), lately, 1)
#        if (a_2 > 0.0): self.opponent_model.agreeable = True
#        else: self.opponent_model.agreeable = False
#        std_deviation = np.std(lately)
#        if (std_deviation > 0.09): self.opponent_model.stability = True
#        else: self.opponent_model.stability = False

    def decide_behaviour(self):
        return "normal"
#        if (self.opponent_model.agreeable and self.opponent_model.stability):
#            behaviour = "conceder"
#        elif (self.opponent_model.agreeable and not self.opponent_model.stability):
#            behaviour = "normal"
#        elif (not self.opponent_model.agreeable and self.opponent_model.stability):
#            behaviour = "hardliner"
#        elif (not self.opponent_model.agreeable and not self.opponent_model.stability):
#            if random.random()<0.5:
#                behaviour = "annoying"
#            else:
#                behaviour = "hardliner"
#        return behaviour



        

