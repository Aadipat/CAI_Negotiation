"""
Wrapper to run GeniusWeb parties as negmas SAONegotiators.

This module provides `GeniusWebNegotiator`, a class that wraps any GeniusWeb
party (DefaultParty subclass) so it can be used in a negmas SAOMechanism.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

try:
    import geniusweb

    _ = geniusweb

    GENIUS_WEB_AVAILABLE = True
except ImportError:
    GENIUS_WEB_AVAILABLE = False

__all__ = ["GENIUS_WEB_AVAILABLE"]

if GENIUS_WEB_AVAILABLE:
    from geniusweb.actions.Accept import Accept
    from geniusweb.actions.Action import Action
    from geniusweb.actions.EndNegotiation import EndNegotiation
    from geniusweb.actions.Offer import Offer
    from geniusweb.actions.PartyId import PartyId
    from geniusweb.inform.ActionDone import ActionDone
    from geniusweb.inform.Agreements import Agreements
    from geniusweb.inform.Finished import Finished
    from geniusweb.inform.Settings import Settings
    from geniusweb.inform.YourTurn import YourTurn
    from geniusweb.issuevalue.Bid import Bid
    from geniusweb.issuevalue.DiscreteValue import DiscreteValue
    from geniusweb.party.DefaultParty import DefaultParty
    from geniusweb.progress.ProgressRounds import ProgressRounds
    from geniusweb.references.Parameters import Parameters
    from geniusweb.references.ProfileRef import ProfileRef
    from geniusweb.references.ProtocolRef import ProtocolRef
    from tudelft_utilities_logging.Reporter import Reporter
    from uri.uri import URI

    from negmas.outcomes import Outcome
    from negmas.preferences.crisp.linear import LinearAdditiveUtilityFunction
    from negmas.sao import SAONegotiator, SAOState, ResponseType
    from negmas.gb.common import GBState

    if TYPE_CHECKING:
        from negmas.situated import Agent
        from negmas.negotiators import Controller
        from negmas.preferences import Preferences
        from negmas.preferences.base_ufun import BaseUtilityFunction

    __all__ += ["GeniusWebNegotiator", "make_geniusweb_negotiator"]

    class _DummyConnection:
        """A dummy connection that captures actions sent by the GeniusWeb party."""

        def __init__(self) -> None:
            self.action: Action | None = None

        def send(self, action: Action) -> None:
            self.action = action

        def reset(self) -> None:
            self.action = None

        def addListener(self, listener: Any) -> None:
            """No-op for dummy connection."""
            pass

        def removeListener(self, listener: Any) -> None:
            """No-op for dummy connection."""
            pass

        def close(self) -> None:
            """No-op for dummy connection."""
            pass

    class _DummyReporter(Reporter):
        """A dummy reporter that silences all logging from GeniusWeb parties."""

        def log(self, *args, **kwargs) -> None:
            pass

    def _sanitize_party_id(name: str) -> str:
        """
        Sanitize a name to be a valid GeniusWeb PartyId.

        GeniusWeb requires party IDs to start with a letter followed by
        zero or more word characters (letters, digits, underscores).
        """
        import re

        # Replace invalid characters with underscores
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        # Ensure it starts with a letter
        if sanitized and not sanitized[0].isalpha():
            sanitized = "p" + sanitized
        # If empty, generate a simple ID
        if not sanitized:
            sanitized = "party" + str(uuid4()).replace("-", "")[:8]
        return sanitized

    def _convert_negmas_ufun_to_geniusweb(
        ufun: LinearAdditiveUtilityFunction,
    ) -> dict[str, Any]:
        """
        Convert a negmas LinearAdditiveUtilityFunction to GeniusWeb profile format.

        Args:
            ufun: A negmas LinearAdditiveUtilityFunction.

        Returns:
            A dictionary representing a GeniusWeb LinearAdditiveUtilitySpace profile.

        Raises:
            ValueError: If the ufun is not a LinearAdditiveUtilityFunction or has no issues.
        """
        if not isinstance(ufun, LinearAdditiveUtilityFunction):
            raise ValueError(
                f"Only LinearAdditiveUtilityFunction is supported, got {type(ufun)}"
            )

        issues = ufun.issues
        if not issues:
            raise ValueError("Utility function must have known issues")

        # Build issue weights (map issue index to weight)
        issue_weights = {}
        for i, w in enumerate(ufun.weights):
            issue_weights[str(i)] = w

        # Build value weights for each issue
        value_weights = {}
        issues_values = {}
        for i, (issue, value_fun) in enumerate(zip(issues, ufun.values)):
            issue_key = str(i)
            value_weights[issue_key] = {}
            issues_values[issue_key] = {"values": []}

            # Enumerate all values for this issue
            for v in issue.all:
                v_str = str(v)
                issues_values[issue_key]["values"].append(v_str)
                # Get the utility for this value from the value function
                u = value_fun(v)
                value_weights[issue_key][v_str] = float(u) if u is not None else 0.0

        # Construct the GeniusWeb profile
        domain = {"name": "negmas_domain", "issuesValues": issues_values}

        issue_utilities = {
            i: {"DiscreteValueSetUtilities": {"valueUtilities": v}}
            for i, v in value_weights.items()
        }

        profile = {
            "LinearAdditiveUtilitySpace": {
                "issueUtilities": issue_utilities,
                "issueWeights": issue_weights,
                "domain": domain,
                "name": "negmas_profile",
            }
        }

        return profile

    def _outcome_to_geniusweb_bid(outcome: Outcome) -> Bid:
        """Convert a negmas Outcome to a GeniusWeb Bid."""
        return Bid({str(i): DiscreteValue(str(v)) for i, v in enumerate(outcome)})

    def _geniusweb_bid_to_outcome(bid: Bid) -> tuple:
        """Convert a GeniusWeb Bid to a negmas Outcome (tuple)."""
        issue_values = bid._issuevalues
        # Sort by issue index to ensure correct order
        sorted_issues = sorted(issue_values.keys(), key=lambda x: int(x))
        return tuple(int(issue_values[i]._value) for i in sorted_issues)

    class GeniusWebNegotiator(SAONegotiator):
        """
        A negmas SAONegotiator that wraps a GeniusWeb party.

        This allows any GeniusWeb DefaultParty subclass to participate in
        negotiations using the negmas SAOMechanism.

        Args:
            party_class: The GeniusWeb party class to wrap (must be a DefaultParty subclass).
            party_params: Optional parameters to pass to the GeniusWeb party.
            preferences: The negotiator's preferences (must be LinearAdditiveUtilityFunction).
            ufun: Alternative way to specify the utility function.
            name: Name for this negotiator.
            parent: Parent controller if any.
            owner: The Agent that owns this negotiator.
            id: Unique identifier for this negotiator.

        Example:
            >>> from negmas import SAOMechanism, make_issue
            >>> from negmas.preferences import LinearAdditiveUtilityFunction
            >>> from geniusweb.basic.boulware_agent.boulware_agent import BoulwareAgent
            >>>
            >>> issues = [make_issue(10, "price"), make_issue(5, "quality")]
            >>> ufun = LinearAdditiveUtilityFunction.random(issues, normalized=True)
            >>> neg = GeniusWebNegotiator(BoulwareAgent, ufun=ufun, name="boulware")
        """

        def __init__(
            self,
            party_class: type[DefaultParty],
            party_params: dict[str, Any] | None = None,
            preferences: Preferences | None = None,
            ufun: BaseUtilityFunction | None = None,
            name: str | None = None,
            parent: Controller | None = None,
            owner: Agent | None = None,
            id: str | None = None,
            **kwargs,
        ):
            super().__init__(
                preferences=preferences,
                ufun=ufun,
                name=name,
                parent=parent,
                owner=owner,
                id=id,
                **kwargs,
            )
            self._party_class = party_class
            self._party_params = party_params or {}
            self._party: DefaultParty | None = None
            self._connection = _DummyConnection()
            self._tmp_dir: Path | None = None
            self._last_received_offer: Outcome | None = None
            self._initialized = False

        def _init_party(self, n_steps: int | None) -> None:
            """Initialize the GeniusWeb party with settings."""
            if self._initialized:
                return

            if not isinstance(self.ufun, LinearAdditiveUtilityFunction):
                raise ValueError(
                    f"GeniusWebNegotiator requires LinearAdditiveUtilityFunction, "
                    f"got {type(self.ufun)}"
                )

            # Create temporary directory for profile storage
            self._tmp_dir = (
                Path(tempfile.gettempdir()) / "geniusweb_negmas" / str(uuid4())
            )
            self._tmp_dir.mkdir(parents=True, exist_ok=True)

            # Store parameters including storage_dir
            params = dict(self._party_params)
            params["storage_dir"] = str(self._tmp_dir)

            # Convert negmas ufun to GeniusWeb profile format and save
            profile_dict = _convert_negmas_ufun_to_geniusweb(self.ufun)
            profile_path = self._tmp_dir / "profile.json"
            with profile_path.open("w") as f:
                json.dump(profile_dict, f)

            # Create the party instance
            # Try with reporter argument first, then without (for ANL2023 agents)
            try:
                self._party = self._party_class(_DummyReporter())
            except TypeError:
                # Agent doesn't accept reporter argument (e.g., ANL2023 agents)
                self._party = self._party_class()

            # Set up the dummy connection (works because we use it as a duck-typed interface)
            self._party._connection = self._connection  # type: ignore[assignment]

            # Create Settings to initialize the party
            raw_id = self.id or self.name or str(uuid4())
            party_id = PartyId(_sanitize_party_id(raw_id))
            # Use forward slashes in file URI to avoid URL-encoding of
            # backslashes on Windows (rfc3986 encodes \ as %5C).
            profile_uri = f"file:{str(profile_path).replace(chr(92), '/')}"
            profile_ref = ProfileRef(URI(profile_uri))
            protocol = ProtocolRef(URI("SAOP"))

            # Use round-based progress
            n_rounds = n_steps if n_steps else 100
            progress = ProgressRounds(
                n_rounds,
                0,
                datetime.now(),
            )

            settings = Settings(
                party_id,
                profile_ref,
                protocol,
                progress,
                Parameters(params),
            )

            # Notify the party of settings
            self._party.notifyChange(settings)

            # Store party ID for creating actions
            self._party_id = party_id
            self._initialized = True

        def on_negotiation_start(self, state: GBState) -> None:
            """Called when negotiation starts. Initializes the GeniusWeb party."""
            super().on_negotiation_start(state)
            n_steps = self.nmi.n_steps if self.nmi else None
            self._init_party(n_steps)

        def on_negotiation_end(self, state: GBState) -> None:
            """Called when negotiation ends. Cleans up the GeniusWeb party."""
            super().on_negotiation_end(state)

            if self._party is not None:
                # Notify party of finish
                if (
                    self._last_received_offer is not None
                    and state.agreement is not None
                ):
                    bid = _outcome_to_geniusweb_bid(state.agreement)
                    agreements = Agreements({self._party_id: bid})
                else:
                    agreements = Agreements({})

                self._party.notifyChange(Finished(agreements))

            # Clean up temp directory
            if self._tmp_dir and self._tmp_dir.exists():
                shutil.rmtree(self._tmp_dir, ignore_errors=True)

            self._party = None
            self._initialized = False

        def _notify_opponent_action(
            self, offer: Outcome, is_accept: bool = False
        ) -> None:
            """Notify the GeniusWeb party of an opponent's action."""
            if self._party is None:
                return

            bid = _outcome_to_geniusweb_bid(offer)
            # Use a placeholder opponent ID
            opponent_id = PartyId("opponent")

            if is_accept:
                action = Accept(opponent_id, bid)
            else:
                action = Offer(opponent_id, bid)

            self._party.notifyChange(ActionDone(action))

        def _get_party_action(self) -> Action | None:
            """Request an action from the GeniusWeb party."""
            if self._party is None:
                return None

            # Clear any previous action
            self._connection.reset()

            # Signal that it's the party's turn
            self._party.notifyChange(YourTurn())

            # Retrieve the action
            action = self._connection.action
            self._connection.reset()

            # Also check if party stored action directly (some implementations do this)
            if action is None and hasattr(self._party, "action"):
                action = getattr(self._party, "action", None)
                setattr(self._party, "action", None)

            return action

        def propose(self, state: SAOState, dest: str | None = None) -> Outcome | None:
            """
            Generate a proposal by delegating to the GeniusWeb party.

            Args:
                state: Current negotiation state.
                dest: Destination negotiator ID (ignored for bilateral).

            Returns:
                An outcome to propose, or None to end negotiation.
            """
            _ = dest

            if not self._initialized:
                self._init_party(self.nmi.n_steps if self.nmi else None)

            # If there's a current offer from opponent, notify the party
            if (
                state.current_offer is not None
                and state.current_offer != self._last_received_offer
            ):
                self._notify_opponent_action(state.current_offer)
                self._last_received_offer = state.current_offer

            # Get action from the party
            action = self._get_party_action()

            if action is None:
                return None

            if isinstance(action, EndNegotiation):
                return None

            if isinstance(action, (Offer, Accept)):
                return _geniusweb_bid_to_outcome(action.getBid())

            return None

        def respond(self, state: SAOState, source: str | None = None) -> ResponseType:
            """
            Respond to an offer by delegating to the GeniusWeb party.

            Args:
                state: Current negotiation state.
                source: Source negotiator ID (ignored for bilateral).

            Returns:
                ResponseType indicating accept, reject, or end negotiation.
            """
            _ = source

            if not self._initialized:
                self._init_party(self.nmi.n_steps if self.nmi else None)

            offer = state.current_offer
            if offer is None:
                return ResponseType.REJECT_OFFER

            # Notify party of the offer if not already done
            if offer != self._last_received_offer:
                self._notify_opponent_action(offer)
                self._last_received_offer = offer

            # Get action from the party
            action = self._get_party_action()

            if action is None:
                return ResponseType.REJECT_OFFER

            if isinstance(action, Accept):
                return ResponseType.ACCEPT_OFFER

            if isinstance(action, EndNegotiation):
                return ResponseType.END_NEGOTIATION

            # Offer means rejection of current offer
            return ResponseType.REJECT_OFFER

    def make_geniusweb_negotiator(
        party_class: type[DefaultParty],
        party_params: dict[str, Any] | None = None,
    ) -> type[GeniusWebNegotiator]:
        """
        Factory function to create a GeniusWebNegotiator subclass for a specific party.

        This is useful when you want to register negotiator types that can be
        instantiated without passing the party_class each time.

        Args:
            party_class: The GeniusWeb party class to wrap.
            party_params: Default parameters for the party.

        Returns:
            A new class that wraps the specified GeniusWeb party.

        Example:
            >>> from environment.agents.geniusweb.basic.boulware_agent.boulware_agent import BoulwareAgent
            >>> BoulwareNegotiator = make_geniusweb_negotiator(BoulwareAgent)
            >>> neg = BoulwareNegotiator(ufun=my_ufun, name="boulware1")
        """

        class _WrappedNegotiator(GeniusWebNegotiator):
            def __init__(
                self,
                preferences: Preferences | None = None,
                ufun: BaseUtilityFunction | None = None,
                name: str | None = None,
                parent: Controller | None = None,
                owner: Agent | None = None,
                id: str | None = None,
                extra_params: dict[str, Any] | None = None,
                **kwargs,
            ):
                merged_params = dict(party_params or {})
                if extra_params:
                    merged_params.update(extra_params)
                super().__init__(
                    party_class=party_class,
                    party_params=merged_params,
                    preferences=preferences,
                    ufun=ufun,
                    name=name,
                    parent=parent,
                    owner=owner,
                    id=id,
                    **kwargs,
                )

        _WrappedNegotiator.__name__ = f"GeniusWeb_{party_class.__name__}"
        _WrappedNegotiator.__qualname__ = f"GeniusWeb_{party_class.__name__}"

        return _WrappedNegotiator
