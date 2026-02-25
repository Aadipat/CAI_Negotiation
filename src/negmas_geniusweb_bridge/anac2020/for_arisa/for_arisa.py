"""
ForArisa Agent - A negotiation agent using genetic algorithm for utility estimation.

This agent was translated from the original Java implementation from ANAC 2020.
Translation was performed using AI assistance.

Original strategy:
- Uses genetic algorithm to estimate utility space from uncertain preferences
- Uses JohnnyBlack opponent modeling (frequency-based)
- Time-dependent concession with fast convergence toward Nash point
- Different acceptance thresholds at different time stages
"""

from __future__ import annotations

import logging
import math
import random
from decimal import Decimal
from typing import TYPE_CHECKING, cast

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
from geniusweb.issuevalue.Value import Value
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter

if TYPE_CHECKING:
    from geniusweb.issuevalue.Domain import Domain


class ValueNew:
    """
    Represents a value with frequency tracking for opponent modeling.

    Tracks how often each value option is selected by the opponent
    and computes the estimated evaluation/weight.
    """

    def __init__(self, value_name: Value):
        """
        Initialize a ValueNew instance.

        Args:
            value_name: The value this tracks.
        """
        self.value_name = value_name
        self.count = 0  # How many times this value was selected
        self.rank = 0  # Rank based on frequency (lower rank = more frequent)
        self.total_of_options = 0  # Total number of options for this issue
        self.count_bid_number = 0  # Total number of bids seen
        self.calculated_value = 0.0  # Computed evaluation for this value
        self.weight_unnormalized = 0.0  # Unnormalized weight contribution

    def compute(self) -> None:
        """Compute the calculated value and weight based on frequency data."""
        if self.total_of_options > 0:
            self.calculated_value = (
                self.total_of_options - self.rank + 1
            ) / self.total_of_options
        else:
            self.calculated_value = 0.0

        if self.count_bid_number > 0:
            temp = self.count / self.count_bid_number
            self.weight_unnormalized = temp * temp
        else:
            self.weight_unnormalized = 0.0


class IaMap:
    """
    Opponent model using JohnnyBlack frequency-based modeling.

    Tracks opponent's value selections and estimates their utility function
    based on frequency of selections.
    """

    def __init__(self, domain: Domain):
        """
        Initialize the opponent model.

        Args:
            domain: The negotiation domain.
        """
        self._domain = domain
        self._issue_value_map: dict[str, list[ValueNew]] = {}
        self._weight_list: dict[str, float] = {}
        self.count_bid_number = 0

        # Initialize the map with all issues and values
        for issue in domain.getIssues():
            value_set = domain.getValues(issue)
            value_list: list[ValueNew] = []
            for value in value_set:
                value_list.append(ValueNew(value))
            self._issue_value_map[issue] = value_list

    def johnny_black(self, last_offer: Bid) -> None:
        """
        Update opponent model with a new bid (JohnnyBlack algorithm).

        Args:
            last_offer: The opponent's bid.
        """
        self.count_bid_number += 1

        # Update frequency counts
        for issue in last_offer.getIssues():
            offer_value = last_offer.getValue(issue)
            if offer_value is None:
                continue

            value_list = self._issue_value_map.get(issue, [])
            for value_new in value_list:
                if str(value_new.value_name) == str(offer_value):
                    value_new.count += 1

                value_new.total_of_options = len(value_list)
                value_new.count_bid_number = self.count_bid_number

            # Sort by count (descending) and assign ranks
            value_list.sort(key=lambda v: v.count, reverse=True)
            for idx, value_new in enumerate(value_list):
                value_new.rank = idx + 1

        # Compute values for all ValueNew objects
        for issue in last_offer.getIssues():
            value_list = self._issue_value_map.get(issue, [])
            for value_new in value_list:
                value_new.compute()

        # Calculate total weight for normalization
        total_weight = 0.0
        for issue in last_offer.getIssues():
            value_list = self._issue_value_map.get(issue, [])
            for value_new in value_list:
                total_weight += value_new.weight_unnormalized

        # Calculate normalized weights for each issue
        if total_weight > 0:
            for issue in last_offer.getIssues():
                issue_weight_unnormalized = 0.0
                value_list = self._issue_value_map.get(issue, [])
                for value_new in value_list:
                    issue_weight_unnormalized += value_new.weight_unnormalized
                issue_weight = issue_weight_unnormalized / total_weight
                self._weight_list[issue] = issue_weight

    def jb_predict(self, bid: Bid) -> float:
        """
        Predict opponent's utility for a bid using JohnnyBlack model.

        Args:
            bid: The bid to evaluate.

        Returns:
            Estimated utility (0-1) for the opponent.
        """
        utility = 0.0

        for issue in bid.getIssues():
            bid_value = bid.getValue(issue)
            if bid_value is None:
                continue

            issue_weight = self._weight_list.get(issue, 0.0)
            value_list = self._issue_value_map.get(issue, [])

            for value_new in value_list:
                if str(value_new.value_name) == str(bid_value):
                    utility += issue_weight * value_new.calculated_value
                    break

        return utility


class GeneticAlgorithm:
    """
    Genetic algorithm for estimating utility space from bid rankings.

    Uses evolutionary optimization to find a utility function that
    best matches the given bid ranking/ordering.
    """

    def __init__(self, domain: Domain, bid_ranking: list[Bid]):
        """
        Initialize the genetic algorithm.

        Args:
            domain: The negotiation domain.
            bid_ranking: List of bids ordered from worst to best.
        """
        self._domain = domain
        self._bid_ranking = bid_ranking
        self._random = random.Random()
        self._pop_size = 500
        self._max_iter_num = 170
        self._mutation_rate = 0.04

        # Build issue structure
        self._issues: list[str] = list(domain.getIssues())
        self._issue_values: dict[str, list[Value]] = {}
        for issue in self._issues:
            values = list(domain.getValues(issue))
            self._issue_values[issue] = values

    def _get_random_chromosome(self) -> dict[str, tuple[float, dict[str, float]]]:
        """
        Generate a random utility space (chromosome).

        Returns:
            A dict mapping issue -> (weight, {value -> evaluation}).
        """
        chromosome: dict[str, tuple[float, dict[str, float]]] = {}
        total_weight = 0.0

        for issue in self._issues:
            weight = self._random.random()
            total_weight += weight
            evaluations: dict[str, float] = {}
            for value in self._issue_values[issue]:
                evaluations[str(value)] = self._random.random()
            chromosome[issue] = (weight, evaluations)

        # Normalize weights
        if total_weight > 0:
            for issue in self._issues:
                old_weight, evals = chromosome[issue]
                chromosome[issue] = (old_weight / total_weight, evals)

        return chromosome

    def _get_utility(
        self, chromosome: dict[str, tuple[float, dict[str, float]]], bid: Bid
    ) -> float:
        """
        Calculate utility of a bid using a chromosome.

        Args:
            chromosome: The utility space representation.
            bid: The bid to evaluate.

        Returns:
            Utility value (0-1).
        """
        utility = 0.0
        for issue in bid.getIssues():
            value = bid.getValue(issue)
            if value is None:
                continue
            weight, evaluations = chromosome.get(issue, (0.0, {}))
            eval_val = evaluations.get(str(value), 0.0)
            utility += weight * eval_val
        return utility

    def _get_fitness(
        self, chromosome: dict[str, tuple[float, dict[str, float]]]
    ) -> float:
        """
        Calculate fitness of a chromosome based on how well it matches bid ranking.

        Uses Spearman-like rank correlation measure.

        Args:
            chromosome: The utility space to evaluate.

        Returns:
            Fitness score (higher is better).
        """
        # Sample bids to reduce computation
        bid_list = self._sample_bids()

        # Calculate utility for each sampled bid
        utility_list = [self._get_utility(chromosome, bid) for bid in bid_list]

        # Create (index, utility) pairs and sort by utility
        indexed_utils = list(enumerate(utility_list))
        indexed_utils.sort(key=lambda x: x[1])

        # Calculate rank error
        error = 0
        for rank, (original_idx, _) in enumerate(indexed_utils):
            gap = abs(original_idx - rank)
            error += gap * gap

        # Convert error to fitness score using logarithmic formula
        n = len(indexed_utils)
        if n > 0:
            x = error / (n**3) if n > 0 else 0
            score = -15 * math.log(x + 0.00001)
        else:
            score = 0.0

        return score

    def _sample_bids(self) -> list[Bid]:
        """
        Sample bids from ranking to reduce computation.

        Returns:
            Sampled list of bids.
        """
        size = len(self._bid_ranking)

        if size <= 400:
            return list(self._bid_ranking)

        # Determine step size based on ranking size
        if size < 800:
            step = 2
        elif size < 1200:
            step = 3
        elif size < 1500:
            step = 4
        elif size < 1600:
            step = 4
        elif size < 2000:
            step = 5
        elif size < 2400:
            step = 6
        elif size < 2800:
            step = 7
        elif size < 3200:
            step = 8
        elif size < 3600:
            step = 9
        elif size < 4000:
            step = 10
        elif size < 4400:
            step = 11
        elif size < 4800:
            step = 12
        elif size < 5200:
            step = 13
        else:
            step = 13

        sampled = []
        for i in range(0, size, step):
            sampled.append(self._bid_ranking[i])
            if len(sampled) >= 400:
                break

        return sampled

    def _select(
        self,
        population: list[dict[str, tuple[float, dict[str, float]]]],
        fitness_list: list[float],
    ) -> list[dict[str, tuple[float, dict[str, float]]]]:
        """
        Select next generation using elitism and roulette wheel selection.

        Args:
            population: Current population.
            fitness_list: Fitness scores for population.

        Returns:
            Selected population for next generation.
        """
        elite_number = 2
        next_population: list[dict[str, tuple[float, dict[str, float]]]] = []

        # Elite selection
        copy_fitness = list(fitness_list)
        for _ in range(elite_number):
            max_fitness = max(copy_fitness)
            idx = copy_fitness.index(max_fitness)
            next_population.append(population[idx])
            copy_fitness[idx] = -1000.0

        # Roulette wheel selection
        sum_fitness = sum(f for f in fitness_list if f > 0)
        if sum_fitness <= 0:
            sum_fitness = 1.0

        for _ in range(self._pop_size - elite_number):
            rand_num = self._random.random() * sum_fitness
            cumulative = 0.0
            selected_idx = 0
            for j, f in enumerate(fitness_list):
                cumulative += max(0, f)
                if cumulative > rand_num:
                    selected_idx = j
                    break
            next_population.append(population[selected_idx])

        return next_population

    def _crossover(
        self,
        father: dict[str, tuple[float, dict[str, float]]],
        mother: dict[str, tuple[float, dict[str, float]]],
    ) -> dict[str, tuple[float, dict[str, float]]]:
        """
        Create child chromosome through crossover and mutation.

        Args:
            father: First parent chromosome.
            mother: Second parent chromosome.

        Returns:
            Child chromosome.
        """
        mutation_step = 0.35
        child: dict[str, tuple[float, dict[str, float]]] = {}
        total_weight = 0.0

        for issue in self._issues:
            w_father, evals_father = father.get(issue, (0.5, {}))
            w_mother, evals_mother = mother.get(issue, (0.5, {}))

            # Crossover weights
            w_union = (w_father + w_mother) / 2
            if self._random.random() > 0.5:
                w_child = w_union + mutation_step * abs(w_father - w_mother)
            else:
                w_child = w_union - mutation_step * abs(w_father - w_mother)
            w_child = max(0.01, w_child)

            # Mutation for weight
            if self._random.random() < self._mutation_rate:
                w_child = self._random.random()

            # Crossover evaluations
            child_evals: dict[str, float] = {}
            for value in self._issue_values[issue]:
                value_str = str(value)
                v_father = evals_father.get(value_str, 0.5)
                v_mother = evals_mother.get(value_str, 0.5)

                v_union = (v_father + v_mother) / 2
                if self._random.random() > 0.5:
                    v_child = v_union + mutation_step * abs(v_father - v_mother)
                else:
                    v_child = v_union - mutation_step * abs(v_father - v_mother)
                v_child = max(0.01, v_child)

                # Mutation for evaluation
                if self._random.random() < self._mutation_rate:
                    v_child = self._random.random()

                child_evals[value_str] = v_child

            child[issue] = (w_child, child_evals)
            total_weight += w_child

        # Normalize weights
        if total_weight > 0:
            for issue in self._issues:
                old_weight, evals = child[issue]
                child[issue] = (old_weight / total_weight, evals)

        return child

    def run(self) -> dict[str, tuple[float, dict[str, float]]]:
        """
        Run the genetic algorithm.

        Returns:
            Best chromosome (utility space) found.
        """
        # Initialize population
        population: list[dict[str, tuple[float, dict[str, float]]]] = []
        for _ in range(self._pop_size * 4):
            population.append(self._get_random_chromosome())

        # Evolution loop
        for _ in range(self._max_iter_num):
            # Calculate fitness
            fitness_list = [self._get_fitness(chrom) for chrom in population]

            # Selection
            population = self._select(population, fitness_list)

            # Crossover (10% of population)
            for _ in range(int(self._pop_size * 0.1)):
                father = population[self._random.randint(0, len(population) - 1)]
                mother = population[self._random.randint(0, len(population) - 1)]
                child = self._crossover(father, mother)
                population.append(child)

        # Select best from final population
        final_fitness = [self._get_fitness(chrom) for chrom in population]
        best_fitness = max(final_fitness)
        best_idx = final_fitness.index(best_fitness)

        return population[best_idx]


class EstimatedUtilitySpace:
    """
    Wrapper for estimated utility space from genetic algorithm.

    Provides utility calculation interface similar to LinearAdditive.
    """

    def __init__(
        self,
        domain: Domain,
        chromosome: dict[str, tuple[float, dict[str, float]]],
    ):
        """
        Initialize the estimated utility space.

        Args:
            domain: The negotiation domain.
            chromosome: The utility space representation from GA.
        """
        self._domain = domain
        self._chromosome = chromosome

    def getUtility(self, bid: Bid) -> Decimal:
        """
        Get utility of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            Utility as Decimal.
        """
        utility = 0.0
        for issue in bid.getIssues():
            value = bid.getValue(issue)
            if value is None:
                continue
            weight, evaluations = self._chromosome.get(issue, (0.0, {}))
            eval_val = evaluations.get(str(value), 0.0)
            utility += weight * eval_val
        return Decimal(utility)

    def getDomain(self) -> Domain:
        """Get the domain."""
        return self._domain


class ForArisa(DefaultParty):
    """
    ForArisa negotiation agent using genetic algorithm for utility estimation.

    This agent uses:
    - Genetic algorithm to estimate own utility space from bid rankings
    - JohnnyBlack frequency-based opponent modeling
    - Time-dependent concession strategy with fast convergence
    - Different acceptance thresholds at different negotiation stages
    """

    MINIMUM_TARGET = 0.83

    def __init__(self, reporter: Reporter | None = None):
        """Initialize the agent."""
        super().__init__(reporter)
        self._last_offer: Bid | None = None
        self._me: PartyId | None = None
        self._profile_interface: ProfileInterface | None = None
        self._progress: Progress | None = None
        self._profile: LinearAdditive | None = None

        # ForArisa specific
        self._ia_map: IaMap | None = None
        self._estimated_space: EstimatedUtilitySpace | None = None
        self._concession_value: float = 1.0
        self._max_bid_for_me: Bid | None = None
        self._domain: Domain | None = None
        self._all_bids: AllBidsList | None = None

    def notifyChange(self, info: Inform) -> None:
        """Handle incoming information from the negotiation protocol."""
        try:
            if isinstance(info, Settings):
                self._handle_settings(info)
            elif isinstance(info, ActionDone):
                self._handle_action_done(info)
            elif isinstance(info, YourTurn):
                self._my_turn()
            elif isinstance(info, Finished):
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
                self.terminate()
        except Exception as e:
            self.getReporter().log(logging.WARNING, f"Failed to handle info: {e}")

    def _handle_settings(self, settings: Settings) -> None:
        """Initialize agent with settings."""
        self._profile_interface = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )
        self._me = settings.getID()
        self._progress = settings.getProgress()

        profile = self._profile_interface.getProfile()
        if isinstance(profile, LinearAdditive):
            self._profile = profile
            self._domain = profile.getDomain()
            self._all_bids = AllBidsList(self._domain)
            self._init_models()

    def _init_models(self) -> None:
        """Initialize genetic algorithm and opponent model."""
        if self._profile is None or self._domain is None:
            return

        # Initialize opponent model
        self._ia_map = IaMap(self._domain)

        # Create bid ranking from utility function
        # In original Java, this came from UserModel.getBidRanking()
        # Here we create it from the profile
        bid_ranking = self._create_bid_ranking()

        # Run genetic algorithm to estimate utility space
        ga = GeneticAlgorithm(self._domain, bid_ranking)
        best_chromosome = ga.run()
        self._estimated_space = EstimatedUtilitySpace(self._domain, best_chromosome)

        # Find max bid
        if bid_ranking:
            self._max_bid_for_me = bid_ranking[-1]  # Best bid (last in ranking)

    def _create_bid_ranking(self) -> list[Bid]:
        """
        Create a bid ranking from the utility profile.

        Returns:
            List of bids sorted from worst to best.
        """
        if self._profile is None or self._all_bids is None:
            return []

        # Sample bids
        total_bids = self._all_bids.size().intValue()
        sample_size = min(total_bids, 500)

        bids_with_util: list[tuple[Bid, float]] = []
        indices = random.sample(range(total_bids), sample_size)
        for i in indices:
            bid = self._all_bids.get(i)
            utility = float(self._profile.getUtility(bid))
            bids_with_util.append((bid, utility))

        # Sort by utility (ascending - worst to best)
        bids_with_util.sort(key=lambda x: x[1])
        return [bid for bid, _ in bids_with_util]

    def _handle_action_done(self, info: ActionDone) -> None:
        """Handle opponent's action."""
        other_action = info.getAction()
        if isinstance(other_action, Offer) and other_action.getActor() != self._me:
            self._last_offer = other_action.getBid()
            # Update opponent model
            if self._ia_map is not None and self._last_offer is not None:
                self._ia_map.johnny_black(self._last_offer)

    def _get_time(self) -> float:
        """Get current normalized time (0-1)."""
        if self._progress is None:
            return 0.0
        return self._progress.get(int(1000 * __import__("time").time()))

    def _calculate_concession(self, time: float) -> None:
        """Calculate concession value based on time."""
        beta = 0.5
        time_pow = time**beta
        self._concession_value = self.MINIMUM_TARGET + (1 - time_pow) * (
            1 - self.MINIMUM_TARGET
        )

    def _get_estimated_utility(self, bid: Bid) -> float:
        """Get estimated utility of a bid."""
        if self._estimated_space is None:
            if self._profile is not None:
                return float(self._profile.getUtility(bid))
            return 0.5
        return float(self._estimated_space.getUtility(bid))

    def _my_turn(self) -> None:
        """Execute agent's turn."""
        time = self._get_time()
        self._calculate_concession(time)

        action: Action | None = None

        if self._last_offer is not None:
            last_util = self._get_estimated_utility(self._last_offer)
            opp_util = (
                self._ia_map.jb_predict(self._last_offer)
                if self._ia_map is not None
                else 0.5
            )

            # Time-dependent acceptance strategy
            if time < 0.3:
                if last_util > self._concession_value or last_util > 0.88:
                    action = Accept(self._me, self._last_offer)
            elif time < 0.5:
                if last_util > self._concession_value or last_util > 0.87:
                    action = Accept(self._me, self._last_offer)
            elif time < 0.7:
                if last_util > self._concession_value or last_util > 0.85:
                    action = Accept(self._me, self._last_offer)
            elif time < 0.8:
                if last_util > self._concession_value or last_util > 0.83:
                    action = Accept(self._me, self._last_offer)
            elif time < 0.85:
                if last_util > self._concession_value or last_util > 0.8:
                    action = Accept(self._me, self._last_offer)
            elif time < 0.9:
                if last_util > self._concession_value or last_util > 0.7:
                    action = Accept(self._me, self._last_offer)
            elif time < 0.93:
                if last_util > self._concession_value or last_util > opp_util:
                    action = Accept(self._me, self._last_offer)
            elif time < 0.98:
                if last_util > self._concession_value or last_util > opp_util:
                    action = Accept(self._me, self._last_offer)
            else:
                # Final moments - accept anything
                action = Accept(self._me, self._last_offer)

        if action is None:
            action = self._generate_bid()

        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()

        self.getConnection().send(action)

    def _generate_bid(self) -> Offer:
        """Generate a bid offer."""
        time = self._get_time()

        if self._all_bids is None or self._domain is None:
            return self._random_bid()

        num_possible = self._all_bids.size().intValue()

        # Early game: send best bid to confuse opponent
        if time < 0.05 and self._max_bid_for_me is not None:
            return Offer(self._me, self._max_bid_for_me)

        # Find bids in acceptable range
        candidate_bids: list[Bid] = []
        candidate_utils: list[float] = []
        candidate_opp_utils: list[float] = []

        search_iterations = 2 * num_possible if time < 0.4 else 3 * num_possible
        search_iterations = min(search_iterations, 5000)

        lower_bound = self._concession_value - (0.1 if time < 0.4 else 0.05)
        upper_bound = self._concession_value + 0.05

        for _ in range(search_iterations):
            random_bid = self._get_random_bid()
            util = self._get_estimated_utility(random_bid)

            if lower_bound < util < upper_bound:
                candidate_bids.append(random_bid)
                candidate_utils.append(util)
                if self._ia_map is not None:
                    candidate_opp_utils.append(self._ia_map.jb_predict(random_bid))
                else:
                    candidate_opp_utils.append(0.5)

        # If no candidates found, generate high utility bids
        if not candidate_bids:
            for _ in range(min(2 * num_possible, 2000)):
                random_bid = self._get_random_bid()
                candidate_bids.append(random_bid)
                candidate_utils.append(self._get_estimated_utility(random_bid))

            if candidate_utils:
                max_util = max(candidate_utils)
                best_idx = candidate_utils.index(max_util)
                return Offer(self._me, candidate_bids[best_idx])
            return self._random_bid()

        # Select bid strategy based on time
        if time < 0.4:
            # Maximize own utility
            max_util = max(candidate_utils)
            best_idx = candidate_utils.index(max_util)
            return Offer(self._me, candidate_bids[best_idx])
        else:
            # Maximize opponent utility (to encourage acceptance)
            if candidate_opp_utils:
                max_opp_util = max(candidate_opp_utils)
                best_idx = candidate_opp_utils.index(max_opp_util)
                return Offer(self._me, candidate_bids[best_idx])
            return Offer(self._me, candidate_bids[0])

    def _get_random_bid(self) -> Bid:
        """Get a random bid from all possible bids."""
        if self._all_bids is None:
            raise ValueError("All bids not initialized")
        total = self._all_bids.size().intValue()
        idx = random.randint(0, total - 1)
        return self._all_bids.get(idx)

    def _random_bid(self) -> Offer:
        """Generate a random bid offer."""
        return Offer(self._me, self._get_random_bid())

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SAOP", "SHAOP"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return (
            "ForArisa: Uses genetic algorithm for utility estimation "
            "with JohnnyBlack opponent modeling (AI-translated from Java)"
        )
