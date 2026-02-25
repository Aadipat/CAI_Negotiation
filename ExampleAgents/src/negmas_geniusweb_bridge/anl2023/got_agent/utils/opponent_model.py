import copy
from collections import defaultdict

from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.DiscreteValueSet import DiscreteValueSet
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
import numpy as np
from sklearn.preprocessing import normalize
from scipy.stats import chisquare


class OpponentModel:
    def __init__(self, domain: Domain, num_issues, num_values_for_each_issue, namesNumbersDict):

        # BELOW ARE HYPERPARAMETERS FIRST
        self.gamma = 0.8 # between 0 and 1, when 1 the time of the offer doesn't affect how strong it is, when closer to 0, first offers are valued a lot more, for values
        self.windowSize = 5 #k = 20
        self.alpha = 0.1 #α is a positive constant, which controls the maximum magnitude of the weight update.
        self.beta = 0.9 #β is another positive constant, which controls the rate at which the weight update decays over time.
        self.p_value_threshold = 0.7
        self.laplace_smoothing_constant = 0.2

        #basic properties
        self.domain = domain
        self.num_issues = num_issues
        self.num_values_for_each_issue = num_values_for_each_issue
        self.progressPercentage = None #np.array, aligns with rounds
        self.namesNumbersDict = namesNumbersDict
        self.num_values_for_each_issue = num_values_for_each_issue #indexing might mess up here, CHECK AGAIN LATER


        # WINDOW CALCULATIONS
        self.windowCount = 0
        self.thisWindow = self.initialize_count_array(num_issues, num_values_for_each_issue)# create a 2D matrix for counting occurrences
        self.prevWindow = self.initialize_count_array(num_issues, num_values_for_each_issue) # create a 2D matrix for counting occurrences
        self.offer_counts_ALL = self.initialize_count_array(num_issues, num_values_for_each_issue) # create a 2D matrix with Laplace smoothing for counting occurrences
        self.issue_weights_this = np.ones(num_issues)/num_issues# None #np.ones(num_issues)/num_issues #or zeros?
        self.issue_weights_prev = np.ones(num_issues)/num_issues #None # first we don't update these
        self.issue_weights_all = np.ones(num_issues)/num_issues #None # first we don't update these

        # for analysis
        self.numBids = 0
        self.first_bid = None
        #self.offer_counts.fill(np.nan) #nan will mean non existent since we might have more values for some issues
        self.issue_weights_guessed_by_round = []
        self.value_weights_guessed_by_round = []

        # after a certain ratio a positive number means it is conceding
        self.agreeable = False
        self.stability = True


        # value weight calculation, not done by windows
        self.value_weights = [] #value weights are not calculated per window
        for i in range(num_issues): #one subarray for each issue
            self.value_weights.append(list(np.ones(num_values_for_each_issue[i])))



    def initialize_count_array(self, num_issues, num_values_for_each_issue):
        max_num_values = max(num_values_for_each_issue)
        array = np.full((num_issues, max_num_values), np.nan)

        # Set the first num_values_for_each_issue[row_num] values of each row to the laplace smoothing constant
        for i, num_values in enumerate(num_values_for_each_issue):
            array[i, :num_values] = 0.01 # 1 instead of 0 because of Laplace smoothing
        return array # create a 2D matrix for counting occurrences

    def update(self, bid, timeprogress, update_opponent_metrics=True): #in our implementation first bid is important since we assume they start with a very high utility for them
        self.numBids = self.numBids+1
        if self.first_bid is None:
            self.first_bid=bid
        dict = bid.getIssueValues()
        bid_in_tuples = []
        #all issues and values updated first

        for issue in dict.keys():
            tuple = self.namesNumbersDict[str(issue)][str(dict[issue])[1:-1]] #positiontuple
            bid_in_tuples.append(tuple)
            self.thisWindow[tuple[0], tuple[1]] = self.thisWindow[tuple[0], tuple[1]]+1
            self.offer_counts_ALL[tuple[0], tuple[1]] = self.offer_counts_ALL[tuple[0], tuple[1]]+1

        row_max = np.nanmax(self.offer_counts_ALL, axis=1)
        for i in np.arange(0, self.num_issues):
            self.update_value_weights(issue_num=i, max_value_issue=row_max[i])

        if self.windowCount == (self.windowSize-1): #time to update weights and switch to a new window
            #print(self.issue_weights_this)
            concession = False
            self.issue_weights_prev = self.issue_weights_this #this is pointing to previous window rn
            if self.numBids > (self.windowSize+1)*2:
                issues_that_didnt_change = []
                for issue in dict.keys(): #for each issue see if there's a significant difference in distribution
                    i = self.namesNumbersDict[issue]["issueNo"]
                    distr_this = self.calculate_freq_distr_for_issue(self.thisWindow[i], i, self.num_values_for_each_issue[i])
                    distr_prev = self.calculate_freq_distr_for_issue(self.prevWindow[i], i, self.num_values_for_each_issue[i])
                    chi_square_stat, p_value = chisquare(distr_this/np.sum(distr_this), f_exp=distr_prev/np.sum(distr_prev))
                    if (p_value > self.p_value_threshold): #approximately same distribution
                        issues_that_didnt_change.append(i)
                    else: #look at value functions and utility
                        issue_utility_prev = np.dot(distr_prev,self.value_weights[i])
                        issue_utility_this = np.dot(distr_this, self.value_weights[i])
                        if (issue_utility_this < issue_utility_prev): concession = True
                    # if there is concession in at least one of the issues
                        if concession == True and len(issues_that_didnt_change) != self.num_issues:
                            for issue_number in issues_that_didnt_change:
                                self.issue_weights_this[issue_number] = self.issue_weights_prev[issue_number] + self.timefactor(timeprogress)
                                self.issue_weights_this = self.issue_weights_this/np.sum(self.issue_weights_this)
            self.windowCount = 0
            self.prevWindow = self.thisWindow
            self.thisWindow = self.initialize_count_array(self.num_issues, self.num_values_for_each_issue) #initialize again to start counting in this window
        else:
            self.windowCount +=1

        self.issue_weights_guessed_by_round.append(list(np.round(self.issue_weights_this, 3)).copy())
        self.issue_weights_guessed_by_round.append(list(np.round(self.issue_weights_this, 3)).copy())

        self.value_weights_guessed_by_round.append(copy.deepcopy(self.value_weights))
        self.value_weights_guessed_by_round.append(copy.deepcopy(self.value_weights))


    def timefactor(self, timeprogress):
        #Δ(t) = α × (1 − t^β)
        #Δ(t) is the change in the weight at time t.
        #α is a positive constant, which controls the maximum magnitude of the weight update.
        #β is another positive constant, which controls the rate at which the weight update decays over time. higher means more decay
        #t represents the time step or iteration in the negotiation process.
        return self.alpha*(1.0-pow(timeprogress, self.beta))

    def calculate_freq_distr_for_issue(self, issue_values_row, issue_num, num_values):
        freq_distr = []
        for v in range(num_values):
            freq_distr.append(issue_values_row[v]/(self.num_values_for_each_issue[issue_num]+self.windowSize))
        return freq_distr

    def update_value_weights(self, issue_num, max_value_issue):
        for value_num in np.arange(0, self.num_values_for_each_issue[issue_num]):
            #print(self.value_weights)
            #print(self.offer_counts_ALL)
            self.value_weights[issue_num][value_num] = np.round((pow(self.offer_counts_ALL[issue_num][value_num], self.gamma)/pow(max_value_issue, self.gamma)), 6)


    def calculate_opponent_utility(self, bid):
        utility = 0
        for issue, value in bid:
            utility += self.issue_weights_this[issue] * self.value_weights[issue][value]
        return utility


    def get_hyperparams_dict(self):
        hyperparams = {"alpha": self.alpha,
                       "beta": self.beta,
                       "gamma": self.gamma,
                       "window_size": self.windowSize,
                       "p_value_threshold": self.p_value_threshold,
                       "laplace_smoothing_constant": self.laplace_smoothing_constant}
        return hyperparams
