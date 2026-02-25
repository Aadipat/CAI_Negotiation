from typing import List, Dict, Optional

from geniusweb.actions.Action import Action
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.Agreements import Agreements
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.session.SessionResult import SessionResult
from geniusweb.protocol.session.SessionState import SessionState
from geniusweb.protocol.session.mopac.MOPACSettings import MOPACSettings
from geniusweb.protocol.session.mopac.PartyStates import PartyStates
from geniusweb.protocol.session.mopac.phase.OfferPhase import OfferPhase
from geniusweb.protocol.session.mopac.phase.OptInPhase import OptInPhase
from geniusweb.protocol.session.mopac.phase.Phase import Phase, PHASE_MAXTIME, \
	PHASE_MINTIME
from geniusweb.references.PartyWithProfile import PartyWithProfile
from geniusweb.utils import val, toTuple


class MOPACState (SessionState):
	'''
	Keeps track of the current {@link Phase}. Adds initializing stuff and
	time/deadline checking. This state does not contain connections, this assumes
	that someone else handles (i.e. {@link NegoProtocol} that and the connections
	with the parties and that negotiation events are just pumped in from there.
	<p>
	This object is a bit tricky. It has two states
	<ol>
	<li>The initial state, where phase=null and connections are being made to all
	parties. At this point, problems can not be handled nicely yet because there
	are no PartyId's for problematic parties
	<li>The working state, where all parties are connected and all problems can
	be connected to an offending party.
	</ol>	
	'''

# 	private final Phase phase; // maybe null while initializing
# 	private final MOPACSettings settings;
# 	private final Map<PartyId, PartyWithProfile> partyprofiles;
# 	private final List<Action> actions;
# 	private final Progress progress;
# 
# 	/**
# 	 * Creates the initial state from the given settings and progress=null
# 	 * 
# 	 * @param settings the {@link SAOPSettings}
# 	 */
# 	public MOPACState(MOPACSettings settings) {
# 		this(null, Arrays.asList(), null, settings, Collections.emptyMap());
# 
# 	}

	def __init__(self, phase:Optional[Phase] ,
			actions:List[Action] ,
			progress:Optional[Progress] ,
			settings:MOPACSettings,
			partyprofiles:Dict[PartyId, PartyWithProfile]): 
		'''
		@param phase         The Phase, or null if still initializing. Phase is
			             set something only after we have connections.
		@param actions       the legal actions that have been done in the
			             negotiation. {@link PartyStates#getActions()} is
			             called to collect the actions after the phase is
			             finished.first action in list is the oldest. This
			             will not contain actions that immediately led to an
			             agreement, because {@link PartyStates} removes the
			             actions that led to an agreement. This MUST NOT
			             contain illegal actions. Parties doing illegal
			             actions are killed and the offending action ends up
			             in the stacktrace. Previous actions of crashed
			             parties remain standing and valid.
		@param progress      the {@link Progress} line. can be null if not yet
			             known. null happens because during initialization
			             phase the protocol first add all connections. During
			             this time, parties may already enter the
			             failed/exception state.
		@param settings  the {@link SAOPSettings}
		@param partyprofiles map with the {@link PartyWithProfile} for connected
		    	         parties. null is equivalent to an empty map.
		'''
		self._phase = phase
		self._actions = actions
		self._progress = progress
		self._settings = settings
		self._partyprofiles = partyprofiles

	def initPhase(self, newprogress:Progress , now:int) -> "MOPACState":
		'''
		Sets the progress for this session and initial phase. Must be called
		after all parties have been connected with
		{@link #with(PartyId, PartyWithProfile)}.
		
		@param newprogress the initial {@link Progress} typically matching the
		                   settings deadline object
		@param now         current time ms since 1970
		
		@return state with the initial partystates , progress set.
		'''
		if self._progress != None or newprogress == None or self._phase != None:
			raise ValueError(
					"progress must be null, newprogress must be not null and phase must be INIT")

		partyStates = PartyStates(self._getPowers())
		firstPhase = OfferPhase(partyStates,
				now + MOPACState._getAvailablePhaseTime(newprogress, now),
				self._settings.getVotingEvaluator())
		return MOPACState(firstPhase, self._actions, newprogress, self._settings,
				self._partyprofiles)

	def getActions(self) -> List[Action]:
		return list(self._actions)

	def getProgress(self) -> Optional[Progress]:
		return self._progress

	def getAgreements(self) -> Agreements: 
		return val(self._phase).getPartyStates().getAgreements();

	def getSettings(self) -> MOPACSettings:
		return self._settings

	def getPartyProfiles(self) -> Dict[PartyId, PartyWithProfile]:
		return dict(self._partyprofiles)

	def  isFinal(self, now:int) -> bool:
		return self._phase != None and val(self._phase).isFinal(now) \
			and not self.isNewPhasePossible(now)

	def getResults(self) -> List[SessionResult]:
		return [SessionResult(self._partyprofiles, self.getAgreements(),
				{}, None)]

	@staticmethod
	def  _getAvailablePhaseTime(aprogress:Progress , now:int) -> int: 
		'''
		@param progress the Progress that needs to be checked
		@param now      current time ms since 1970
		@return the max possible duration in ms of a phase considering the
		        progress.
		'''
		return min(int(aprogress.getTerminationTime().timestamp() * 1000) - now,
				PHASE_MAXTIME)

	def With(self, id:PartyId , partyprofile:PartyWithProfile) -> "MOPACState":
		'''
		@param id           the new {@link PartyId}
		@param partyprofile the {@link PartyWithProfile} that is associated with
		                    this state
		@return new {@link MOPACState} with the new party added. This call
		        ignores the progress (does not check isFinal) because we uses
		        this during the setup where the deadline is not yet relevant.
		'''
		if self._phase != None:
			raise ValueError(
					"Adding connections only allowed while initializing");

		newprofiles = dict(self._partyprofiles)
		newprofiles[id] = partyprofile
		return MOPACState(None, self._actions, self._progress, self._settings, newprofiles)
	
	def WithException(self, e:ProtocolException) -> "MOPACState":
		'''
		@param e the {@link ProtocolException} that occured
		@return a new state with the error set. You MUST have called
		        {@link #initPhase(Progress, long)} before using this
		'''
		return MOPACState(val(self._phase).WithException(e), self._actions, self._progress,
						self._settings, self._partyprofiles)

	def nextPhase(self, now:int) -> "MOPACState":
		'''
		Start the next phase. If new phase is OfferPhase, we increase progress.
		Actions is reset to empty. does nothing if not
		{@link #isNewPhasePossible(long)}
		
		@param now current time
		@return new {@link MOPACState} with phase initialized for next phase.
		'''
		remainingNegoTime = int(val(self._progress).getTerminationTime().timestamp() * 1000) - now
		newphase = val(self._phase).next(now, min(remainingNegoTime, PHASE_MAXTIME))

		return MOPACState(newphase, self._actions,
					MOPACState._increment(val(self._progress), val(self._phase)),
				self.getSettings(), self._partyprofiles)

	def isNewPhasePossible(self, now:int) -> bool:
		'''
		When this is called, all parties should have acted.
		
		@param now current time
		@return true if there are still &gt;2 parties active and we have enough
		        time for a new phase.
		'''
		# System.out.println("phase=" + phase);
		newprogress = MOPACState._increment(val(self._progress), val(self._phase))
		if newprogress.isPastDeadline(now + PHASE_MINTIME):
			return False

		return len(val(self._phase).getPartyStates().getNegotiatingParties()) >= 2\
				and self._getAvailablePhaseTime(newprogress,
						now) > PHASE_MINTIME

	def getPhase(self) -> Phase:
		return val(self._phase)

	def WithAction(self, actor:PartyId, action:Action, now:int) -> "MOPACState":
		'''
		Check if action is allowed. Add action to the list of actions. Notice,
		this does NOT check if we need to step to the next phase, because
		deciding that is also depending on time-outs.
		
		@param actor  the actor that did this action. Can be used to check if
		              action is valid. NOTICE caller has to make sure the current
		              state is not final. MUST NOT be null.
		@param action the action that was proposed by actor. MUST NOT be null.
		@param now    the current time in ms since 1970, see
		              {@link System#currentTimeMillis()}
		@return new {@link MOPACState} with the action checked and registered. If
		        the action is not allowed, the new state may be that the actor is
		        in the exception list.
		'''
		return MOPACState(val(self._phase).With(actor, action, now), self._actions, self._progress,
				self._settings, self._partyprofiles)

	@staticmethod
	def _increment(aprogress:Progress , aphase:Phase) -> Progress:
		'''
		@param aprogress the progress that might need to be advanced
		@param aphase    the phase
		@return the next progress. Progress round advances if phase is
		        {@link OptIn}.
		'''
		if isinstance(aprogress, ProgressRounds) and isinstance(aphase, OptInPhase):
			return aprogress.advance()
		return aprogress

	def _getPowers(self) -> Dict[PartyId, int]:
		'''
		@return the power of all parties as set in their parameters, default =1.
		    bad power values (non-integer, or <1) are ignored.
		'''
		map:Dict[PartyId, int] = {}
		for pid in self._partyprofiles:
			if self._partyprofiles[pid].getParty().getParameters().containsKey("power"):
				power = self._partyprofiles[pid].getParty().getParameters()\
					.get("power")
				if  not isinstance(power, int) or power < 1:
					power = 1
			else:
				power = 1
			map[pid] = power
		return map

	def __repr__(self) -> str:
		return "MOPACState[" + str(self._phase) + "," + str(self._settings)\
			+"," + str(self._partyprofiles) + "," + str(self._progress) + "]"

	def finishPhase(self) -> "MOPACState":
		'''
		@return a wrapped-up state, with all parties doen an action or kicked,
		        and agreements collected
		'''
		newphase = val(self._phase).finish()
		newactions = list(self._actions)
		newactions = newactions + newphase.getPartyStates().getActions()
		return MOPACState(newphase, newactions, self._progress, self._settings,
				self._partyprofiles)

	def __hash__(self):
		return hash((tuple(self._actions), toTuple(self._partyprofiles),
					self._phase, self._progress, self._settings))
	
	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			 and self._actions == other._actions\
			 and self._partyprofiles == other._partyprofiles\
			 and self._phase == other._phase\
			 and self._progress == other._progress\
			 and self._settings == other._settings

