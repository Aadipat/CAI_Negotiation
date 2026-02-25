

from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.DiscreteValue import DiscreteValue
import random
import numpy as np

class GeneticAlgorithm:
    def __init__(self, generation_num, population_size, max_oppo_bids, domain_issues, domain_issues_values, our_issue_weights, our_value_weights):
        self.generation_num = generation_num
        self.population_size = population_size
        self.all_bids = []
        self.elits = []
        self.non_elits =[]
        self.mutation_rate = 0.2
        self.crossover_rate = 0.5
        self.opponent_bids = []
        self.current_generation = []
        self.max_oppo_bids = max_oppo_bids

        self.domain_issues = list(domain_issues)
        self.domain_issue_value_num = dict()
        self.domain_values = dict()
        self.initialize_domain_values(domain_issues_values)

        self.utilities = set()

        self.my_issue_weights = dict()
        self.assign_my_issue_weights(our_issue_weights)

        self.my_value_weights = dict()
        self.assign_my_value_weights(our_value_weights)

        self.process_percentage = 0

        self.oppo_issue_weights = dict()
        self.initialize_issue_weights()

        self.oppo_value_weights = dict()
        self.initialize_value_weights()

        self.generate_first_gen()
        self.parent_one = self.current_generation
        self.parent_two = self.current_generation
        self.calcScore = None
        self.calcScore = self.calculate_my_utility

        self.estimated_utilities_per_round = []
        self.conceding_slope=0.25
        self.last_y_value=1.0

        self.stage=0
        self.stage_periods=[0.25,0.5,0.75,1]
        self.mutation_rate_array=[0.2,0.1,0.07, 0.07]
        self.crossover_rate_array=[0.5,0.2,0.5,0.5]
        self.calcScore_array=[self.calculate_my_utility,self.concede_my_utility,self.concede_my_utility,self.concede_my_utility]
        self.parent_one_array=[self.current_generation, self.current_generation, self.opponent_bids,self.opponent_bids]
        self.parent_two_array=[self.current_generation, self.opponent_bids, self.opponent_bids, self.opponent_bids]
        self.generation_num_array=[2,3,3,3]

        self.typ = "normal"


# =====================================================================================================================
#===============================CHANGE PARAMETERS ACCORDING TO NEGOTIATION STAGE=======================================
# =====================================================================================================================
    def change_typ(self, typ:str= "normal"):
        #if self.typ == typ:
        #     return
        typ = "normal" #this feature was ommitted for competition
        if typ == "conceder":
            self.last_y_value=((self.conceding_slope+0.80)*self.process_percentage)+self.last_y_value
            self.conceding_slope=-0.80

        elif typ == "normal":
            self.last_y_value=((self.conceding_slope+0.27)*self.process_percentage)+self.last_y_value
            self.conceding_slope=-0.27

        elif typ == "hardliner":
            self.last_y_value=((self.conceding_slope+0.10)*self.process_percentage)+self.last_y_value
            self.conceding_slope=-0.1

        elif typ == "annoying":
            self.last_y_value=((self.conceding_slope-0.50)*self.process_percentage)+self.last_y_value
            self.conceding_slope=0.5

        else:
            print("THIS IS NOT A VALID BEHAVIOUR TYPE")
        #print(self.conceding_slope,"x +",self.last_y_value)

    def assign_for_stage(self):
        self.mutation_rate=self.mutation_rate_array[self.stage]
        self.crossover_rate=self.crossover_rate_array[self.stage]
        self.calcScore=self.calcScore_array[self.stage]
        self.parent_one=self.parent_one_array[self.stage]
        self.parent_two=self.parent_two_array[self.stage]
        self.generation_num=self.generation_num_array[self.stage]

    # _______________________FIND BID____________________________

    def find_bid(self):
        # if self.process_percentage<0.1:
        #     random my gen, my best util
        if len(self.opponent_bids)<1:
            selected_bid = random.choice(self.current_generation)
            self.estimated_utilities_per_round.append(self.calculate_my_utility(selected_bid))

            return self.bid_to_Bid(selected_bid)
        else:

            sample = self.generate_sample()
#            i = int(random.uniform(0,3))
            #print("oppo_bid_num=",len(self.opponent_bids)," my=", self.calculate_my_utility(sample[0]), " oppo=", self.calculate_opponent_utility(sample[0]), " bid=",  collections.OrderedDict(sorted(sample[0].items())))
            self.estimated_utilities_per_round.append(sample[0])

            return self.bid_to_Bid(sample[0])

# =============================MAIN BIDDING STRATEGY=================================
# changing the parameters according to how far we are on the negotation stage
    def change_process_percentage(self, current_process_percentage):
        self.process_percentage=current_process_percentage

        prev_stage = self.stage
        if self.process_percentage<0.03:
            self.stage=0

        elif self.process_percentage<0.2:
            self.stage=1

        elif self.process_percentage<0.4:
            self.stage=2
        else:
            self.stage=3

        if self.stage != prev_stage:
            self.assign_for_stage()


# =====================================================================================================================
# ==============================    CREATING           GENERATIONS        =============================================
# =====================================================================================================================

    def generate_sample(self):
        newGen = []
        for l in range(self.generation_num):
            for i in range(100):
                chrom1 = random.choice(self.parent_one)
                chrom2 = random.choice(self.parent_two)

                a = self.crossover_bid(chrom1, chrom2)
                curScore = np.round(self.calcScore(a),4)
                mutated_a = self.mutate_bid(a)
                if curScore not in self.utilities:
                    newGen.append(a)
                    self.utilities.add(curScore)
                curScore = np.round(self.calcScore(mutated_a),4)
                if curScore not in self.utilities:
                    newGen.append(mutated_a)
                    self.utilities.add(curScore)

            newGen.sort(key=self.calcScore, reverse=True)
            newGen = newGen[:10]
            # random.shuffle(newGen)
            self.current_generation = newGen.copy()
            self.parent_one=self.current_generation
            newGen.clear()
            self.utilities=set()
        return self.current_generation

# =====================================================================================================================
# ==============================          FITNESS FUNCTIONS        =============================================
# =====================================================================================================================
    def calculate_social_welfare(self, bid):
        return self.calculate_my_utility(bid)+self.calculate_opponent_utility(bid)

    def nash_product(self, bid):
        return self.calculate_my_utility(bid)*self.calculate_opponent_utility(bid)

    # the smaller, the better, so size matters
    def kalai_smordinsky(self,bid):
        return (2-abs(self.calculate_my_utility(bid)-self.calculate_opponent_utility(bid)))

    def calculate_both_utilities(self, bid):
        return self.calculate_my_utility(bid)+self.calculate_opponent_utility(bid)

    # Linear Conceding with progress percentage
    def concede_my_utility(self, bid):
        utility = 0

        for issue, value in bid.items():
            utility += self.my_issue_weights[issue] * self.my_value_weights[issue][value]
        utility = 1.0-(abs(utility-(self.last_y_value+(self.conceding_slope*self.process_percentage))))
        return utility

    # Linear Conceding with bid num
    def concede_my_utility2(self, bid):
        utility = 0

        for issue, value in bid.items():
            utility += self.my_issue_weights[issue] * self.my_value_weights[issue][value]
        utility = 1-(abs(utility-(1.0-(0.001*len(self.opponent_bids)))))
        return utility

# =====================================================================================================================
# ___________________________BEHAVIOUR MODELLING CHANGING PARAMETERS________________________________
# =====================================================================================================================

    # NOT IN USE ANYMORE, OMITTED

# =====================================================================================================================
# ___________________________UNIMPORTANT BASIC GENETIC ALGO FUNCTION________________________________
# =====================================================================================================================

# ___________________________BASIC UTILITY CALCULATION________________________________

    def calculate_my_utility(self, bid):
        utility = 0

        for issue, value in bid.items():
            utility += self.my_issue_weights[issue] * self.my_value_weights[issue][value]
        return utility


    def calculate_opponent_utility(self, bid):
        utility = 0

        for issue, value in bid.items():
            utility += self.oppo_issue_weights[issue] * self.oppo_value_weights[issue][value]
        return utility



# --------------------------------------FIRST GENERATION-----------------------------------------
    def generate_first_gen(self):
        for count in range(0,500):
            bid = dict()
            for issue in self.domain_issues:
                bid[issue]= random.choice(self.domain_values[issue])
            curScore = np.round(self.calculate_my_utility(bid),4)
            if curScore not in self.utilities:
                self.current_generation.append(bid)
                self.utilities.add(curScore)
        self.current_generation.sort(key=self.calculate_my_utility, reverse = True)
        self.current_generation = self.current_generation[:20]
        self.elits=self.current_generation
        self.parent_one=self.current_generation
        self.parent_two=self.current_generation
        self.utilities=set()

    # ______________________________________DOMAIN________________________________________________

    # initializes all the value weights to zero
    def initialize_domain_values(self, domain_issue_values):
        for issue in self.domain_issues:
            values_list = []
            count = 0;
            for value in domain_issue_values[issue].getValues():
                values_list.append(value.getValue())
                count = count + 1
            self.domain_values[issue] = values_list
            self.domain_issue_value_num[issue] = count

 # _______________________________________MY WEIGHTS___________________________________
    def assign_my_issue_weights(self, our_issue_weights):
        for key in self.domain_issues:
            self.my_issue_weights[key] = float(our_issue_weights[key])

    def assign_my_value_weights(self, our_value_weights):
        for issue in self.domain_issues:
            values_dict = dict()

            for key in our_value_weights[issue].getUtilities().keys():
                values_dict[key.getValue()]=float(our_value_weights[issue].getUtilities()[key])

            self.my_value_weights[issue] = values_dict


 # _______________________________________OPPONENT___________________________________
 # initializes all the issue weights to zero
    def initialize_issue_weights(self):
        for key in self.domain_issues:
            self.oppo_issue_weights[key] = 0.0
    # initializes all the value weights to zero
    def initialize_value_weights(self):
        for issue in self.domain_issues:
            values_dict = dict()
            for value in self.domain_values[issue]:
                values_dict[value]= 0.0
            self.oppo_value_weights[issue] = values_dict

    def edit_all_weights(self, namesNumberDict, issue_weights, value_weights):
        for issue in self.domain_issues:
            issuNo = namesNumberDict[issue]["issueNo"]
            self.oppo_issue_weights[issue] = issue_weights[issuNo]
            for value in self.domain_values[issue]:
                a, valueNo = namesNumberDict[issue][value]
                self.oppo_value_weights[issue][value] = value_weights[issuNo][valueNo]



    # __________________________MUTATION & CROSSOVER__________________________________

    def mutate_bid(self, bid):
        bid1 = bid.copy()
        for issue, value in bid.items():
            if random.random()<=self.mutation_rate:
                bid1[issue]= random.choice(self.domain_values[issue])
        return bid1

    def mutate_bid2(self, bid):
        mutate_bid_num= int(self.mutation_rate*len(self.domain_issues))
        bid1 = bid.copy()
        for issue in random.sample(self.domain_issues, mutate_bid_num):
                bid1[issue]= random.choice(self.domain_values[issue])
        return bid1

    def crossover_bid(self, bid_a, bid_b):
        crossover_bid_num= int(self.crossover_rate*len(self.domain_issues))
        bid_a1 = bid_a.copy()

        for issue in random.sample(self.domain_issues, crossover_bid_num):
                bid_a1[issue] = bid_b[issue]
        return bid_a1

    def crossover_bid2(self, bid_a, bid_b):
        bid_a1 = bid_a.copy()
        bid_b1 = bid_b.copy()
        crossover_bid_num= int(self.crossover_rate*len(self.domain_issues))
        for issue in random.sample(self.domain_issues, crossover_bid_num):
            temp = bid_a1[issue]
            bid_a1[issue] = bid_b1[issue]
            bid_b1[issue]=temp
        return bid_a1, bid_b1

#     ________________________AGENT HELPER METHODS________________________________
    def add_opponent_bid(self, bid: Bid):
        bidd=self.bid_to_bid(bid)

        bol = False
        for d in self.opponent_bids:
            if d == bol:
                bol=True
                break
        if bol == False:
            self.opponent_bids.append(bidd)
        self.estimated_utilities_per_round.append(self.calculate_opponent_utility(bidd))

#-------------------------------------------PARETO OPTIMALITY------------------------------------------
    def return_pareto_optimal_list(self, bids, x_min):
        xs = []
        ys = []
        util_to_bid = dict()
        ret_list = []
        for bid in bids:
            my_util = self.calculate_my_utility(bid)
            oppo_util = self.calculate_opponent_utility(bid)
            if my_util <= x_min:
                continue
            util_to_bid[(my_util, oppo_util)] = bid

        for key1, value1 in util_to_bid.items():
            is_pareto = True
            for key2, value2 in util_to_bid.items():
                if key1 != key2 and value1[0]<= value2[0] and value1[1]<= value2[1]:
                    is_pareto = False
                    break
            if is_pareto:
                ret_list.append(value1)
        return ret_list


    # _________________________Bid to bid & bid to Bid_______________________________
    def bid_to_bid(self, bid:Bid):
        ret_bid = dict()
        issues = bid.getIssues()
        for issue in issues:
            ret_bid[issue] = bid.getValue(issue).getValue()
        return ret_bid


    def bid_to_Bid(self, bid: dict()):
        dictObj = dict()
        for issue in bid.keys():
            dictObj[issue] = DiscreteValue(bid[issue])
        return Bid(dictObj)



if __name__ == '__main__':
    print("PLIz")


