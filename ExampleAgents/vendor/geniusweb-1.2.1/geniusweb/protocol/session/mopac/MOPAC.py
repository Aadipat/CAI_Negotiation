import logging
from threading import Timer
import threading
from time import time, sleep
from typing import Optional, List

from tudelft.utilities.listener.DefaultListenable import DefaultListenable
from tudelft.utilities.listener.Listener import Listener
from tudelft.utilities.repository.NoResourcesNowException import NoResourcesNowException
from tudelft_utilities_logging.Reporter import Reporter
from uri.uri import URI

from geniusweb.actions.Action import Action
from geniusweb.events.ProtocolEvent import ProtocolEvent
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Settings import Settings
from geniusweb.progress.ProgressFactory import ProgressFactory
from geniusweb.protocol.CurrentNegoState import CurrentNegoState
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.partyconnection.ProtocolToPartyConn import ProtocolToPartyConn
from geniusweb.protocol.partyconnection.ProtocolToPartyConnFactory import ProtocolToPartyConnFactory
from geniusweb.protocol.partyconnection.ProtocolToPartyConnections import ProtocolToPartyConnections
from geniusweb.protocol.session.SessionProtocol import SessionProtocol
from geniusweb.protocol.session.mopac.MOPACState import MOPACState
from geniusweb.references.PartyWithProfile import PartyWithProfile
from geniusweb.references.ProtocolRef import ProtocolRef
from geniusweb.references.Reference import Reference
from geniusweb.utils import val


MINDURATION = 100
MIN_SLEEP_TIME = 1000
MAX_SLEEP_TIME = 60000
MOPACPROTOCOL = ProtocolRef(URI("MOPAC"))


class MOPAC (DefaultListenable[ProtocolEvent], SessionProtocol):
	'''
	All parties are first sent the {@link SessionSettings}. Only parties
	specified initially in the settings do participate (no late joining in)
	
	<h2>parameter</h2> MOPAC parties can receive a parameter <code>power</code>
	containing a Integer. This parameter is picked up by this protocol, for
	handling the agreement extraction from the offers. Power=1 for parties that
	do not have the power parameter.
	<h2>Protocol steps</h2>
	
	<ol>
	<li>The protocol tries to start all parties. If not all parties start, the
	parties are freed up and another attempt is done to start all parties some
	time later.
	<li>The session deadline clock now starts ticking.
	<li>remainingparties are sent their settings.
	<li>Loop until {@link Deadline} is reached or |remainingparties| &le; 2:
	<ol>
	<li>protocol sends {@link YourTurn} to all remainingparties. Each party now
	must submit an {@link Offer} within {@link Phase#PHASE_MAXTIME} seconds. If a
	party fails to submit it is removed from from remainingparties.
	<li>protocol sends a {@link Voting} containing a List of Bid containing all
	received {@link Bid}s. Each party must place his {@link Votes} within the
	provided deadline. If a party does not submit, it is terminated and removed
	from remainingparties. Previous votes for the same bid do not count. But see
	{@link Agreements}. A party that misbehaves after submitting its vote is
	removed but it Votes remain standing.
	<li>protocol sends to all remainingparties a OptIn containing all received
	votes. Each party now must submit again a {@link Votes} object within the
	deadline. This new Votes must equal or extend the previous Votes of the
	party.
	<li>The protocol uses the {@link Phase#getEvaluator()} to determine the
	agreements from the votes. If there are agreements, the parties that placed
	these votes reached an agreement. They are moved to the agreement set and
	removed from the remainingparties.
	</ol>
	<li>Any remaining parties are sent a {@link Finished} object without
	agreement bid and are terminated.
	</ol>
	<p>
	A party can send {@link EndNegotiation} at any time to remove itself from the
	negotiation. The other parties may continue anyawy without him.
	<p>
	Parties receive the {@link Finished} information at the very end when all
	agreements have been collected.
	<p>
	This logs to "Protocol" logger if there are issues
	<p>
	This object is mutable: the internal state changes as parties interact with
	the protocol.
	<p>
	Threadsafe: all entrypoints are synhronized.
	'''
	# Tech notes. 0. Everything here is phase driven and runs due to callback
	# from parties. 1. Connect all parties. 2. If any party fails at any time,
	# add it to exceptions list in the state 3. Run timer to check the phase at
	# possible end time. The timer just checks the state, and therefore it does
	# no harm if it is double checked. 4. We run phases always with either
	# PHASE_TIME or time to the global deadline, whichever comes first.
	# Therefore phases naturally end at end of nego. 5. Phases must have at
	# least {@link #MINDURATION} otherwise it makes no sense to even start it.

	_state:Optional[MOPACState]  = None; # mutable!
	
	# the existing party connections. we assume ownership of this so it should
	# not be modified although connections may of course break. mutable!
	_connections:ProtocolToPartyConnections = ProtocolToPartyConnections([])

	# Set to true after all is done: we sent final outcomes. This is needed
	# because we can't tell from state what we did at the very end.
	_finished = False
	_timer = None

	_synclock = threading.RLock()

	def __init__(self, state:MOPACState , logger:Reporter ):
		'''
		@param state  normally the initial state coming from SAOPSettings
		@param logger the {@link Reporter} to use
		'''
		super().__init__()
		if state == None:
			raise ValueError("state must be not null")
		if state.getSettings().getDeadline().getDuration() < MINDURATION:
			raise ValueError(
					"Duration must be at least " + str(MINDURATION))
		if logger == None :
			raise ValueError("Logger must be not null")

		self._log = logger
		self._state = state

	def start(self, connectionfactory:ProtocolToPartyConnFactory ) :
		with self._synclock:
			try:
				self._connect(connectionfactory)
			except Exception as e:
				# We can't {@link #handleError} yet. FIXME 
				raise ConnectionError("Failed to connect", e);
			
			now = int(1000*time()) 
			self._state = val(self._state).initPhase(
					ProgressFactory.create(val(self._state).getSettings().getDeadline(), now),
					now);
			self._setupParties()
			self._startPhase(now)

	def getDescription(self)->str:
		return "All parties get YourTurn. They now can submit their Offer within 30 seconds. "\
				+ "Next they receive a Voting. They can now submit their Votes."\
				+ "Then they receive a a OptIn, now they can widen up their Votes."\
				+ "If one of their Vote succeeds, they finish with an agreement. "\
				+ "The VotingEvaluator setting determines the exact voting behaviour "\
				+ "and if this process repeats"

	def addParticipant(self, party:PartyWithProfile ):
		raise ValueError("Dynamic joining a negotiation is not supported in AMOP")

	def getState(self)->MOPACState :
		return val(self._state)

	def getRef(self)->ProtocolRef :
		return MOPACPROTOCOL


	#*******************************************************************
	# private functions. Some are protected only, for testing purposes
	# ********************************************************************/
	def _connect(self, connectionfactory:ProtocolToPartyConnFactory ):
		'''
		step 1 in protocol: connect all involved parties and start the clock.
		This always "succeeds" with a valid (but possibly final) state
		<p>
		This is 'protected' to allow junit testing, this code is not a 'public'
		part of the interface.
		
		@param connectionfactory the connectionfactory for making party
		         connections
		
		@throws InterruptedException if the connection procedure is unterrupted
		
		@throws IOException          if this fails to properly conect to the
		             parties, eg interrupted or server not
		             responding..
		'''
		with self._synclock:
			participants = val(self._state).getSettings().getAllParties()
			parties:List[Reference] = \
				[parti.getParty().getPartyRef() for parti in participants]
			self._log.log(logging.INFO, "MOPAC connect " + str(parties))
			newconnections:Optional[List[ProtocolToPartyConn]]  = None

			while newconnections == None: 
				try:
					newconnections = connectionfactory.connectAll(parties)
				except NoResourcesNowException as e:
					waitms = int(1000*e.getLater().timestamp()) - int(1000*time())
					self._log.log(logging.INFO,
							"No resources available to run session, waiting"
									+ str(waitms))
					sleep(min(MAX_SLEEP_TIME,
							max(MIN_SLEEP_TIME, waitms))/1000.)

			for i in range(len(participants)):
				conn = val(newconnections)[i]
				self._connections = self._connections.With(conn)
				self._state = val(self._state).With(conn.getParty(), participants[i])

	def _setupParties(self) :
		'''
		step 2 in protocol: listen to connections and send settings to the
		parties.
		<p>
		This is 'protected' to allow junit testing, this code is not a 'public'
		part of the interface.
		'''
		this=self
		with self._synclock:
			for conn in self._connections:
				
				class ActListener(Listener[Action]):
					def __init__(self, conn):
						self._conn=conn
					def notifyChange(self, action: Action):
				 		 this._actionRequest(self._conn, action, int(1000*time()))

				conn.addListener(ActListener(conn))

			for connection in self._connections:
				try:
					self._sendSettings(connection)
				except ConnectionError as e:
					self._state = val(self._state).WithException(ProtocolException("Failed to initialize",
							connection.getParty()))

	def _startPhase(self, now:int):
		'''
		Send the {@link Inform} for the current phase to the remaining parties
		and start the time-out checker
		'''
		info = val(self._state).getPhase().getInform()
		for pid in val(self._state).getPhase().getPartyStates().getNotYetActed() :
			try:
				val(self._connections.get(pid)).send(info)
			except ConnectionError as e:
				self._state = val(self._state).WithException(ProtocolException(
						"Party seems to have disconnected", pid, e))
		self._startTimer(1 + val(self._state).getPhase().getDeadline() - now)

	def _startTimer(self, deadln:int):
		'''
		Check at given deadline if we already ended the phase.
		
		@param deadn the deadline (ms from now)
		'''
		if self._timer != None:
			raise ValueError("Timer is still running!")
		self._timer = Timer(deadln/1000.0, self._timertask)
		self._timer.start()
	
	def _timertask(self):
		self._checkEndPhase(int(1000*time()))

	def _sendSettings(self, connection:ProtocolToPartyConn):
		'''
		Inform a party about its settings
		
		@param connection
		@throws ConnectionError if party got disconnected
		'''
		with self._synclock:
			partyid = connection.getParty()
			profile = val(self._state).getPartyProfiles()[partyid].getProfile()
			params = val(self._state).getPartyProfiles()[partyid].getParty().getParameters()
			connection.send(Settings(connection.getParty(), profile,self.getRef(),
					val(val(self._state).getProgress()), params));

	def _actionRequest(self, partyconn:ProtocolToPartyConn , action:Action ,
			now:int):
		'''
		This is called when one of the {@link ProtocolToPartyConn}s does an
		action. Synchronized so that we always handle only 1 action at a time.
		
		@param partyconn the connection on which the action came in
		@param action    the {@link Action} taken by some party
		@param now       current time
		'''
		with self._synclock:
			if self._finished:
				return
			self._state = val(self._state).WithAction(partyconn.getParty(), action, now)
			self._checkEndPhase(int(1000*time()))

	def _checkEndPhase(self, now:int) :
		'''
		The current phase may be completed. We check, because it may already been
		handled. Proceed to next phase as needed. Reset the deadline timers and
		inform parties. Increase progress if necessary. Must only be called
		through {@link #endPhase} to ensure this is called only once.
		'''
		with self._synclock:
			if not val(self._state).getPhase().isFinal(now):
				return
			# phase indeed ended. Check what's up.
			if self._timer != None:
				val(self._timer).cancel()
				self._timer = None
			self._state = val(self._state).finishPhase()
			if self._state.isFinal(now):
				print("state "+str(self._state)+" is final")
				self._endNegotiation()
				return
	
			self._state = self._state.nextPhase(now)
	
			self._startPhase(now)

	def _endNegotiation(self):
		'''
		To be called when we reach final state. Must only be called if
		{@link MOPACState#isFinal(long)}. Send finished info to all parties.
		Double calls are automatically ignored using the global finished flag.
		'''
		with self._synclock:
			if self._finished:
				return
			self._finished = True
			info = Finished(self._state.getAgreements())
			for conn in self._connections:
				try:
					conn.send(info)
					conn.close()
				except Exception as  e:
					self._log.log(logging.INFO, "Failed to send Finished to " + str(conn), e)
			self.notifyListeners(CurrentNegoState(self._state))
