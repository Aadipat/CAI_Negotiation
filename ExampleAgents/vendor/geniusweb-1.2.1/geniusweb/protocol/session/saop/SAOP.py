from datetime import datetime
import logging
from threading import Timer
import threading
import time
import traceback
from typing import Optional, List

from tudelft.utilities.listener.DefaultListenable import DefaultListenable
from tudelft.utilities.listener.Listener import Listener
from tudelft.utilities.repository.NoResourcesNowException import NoResourcesNowException
from tudelft_utilities_logging.Reporter import Reporter
from uri.uri import URI

from geniusweb.actions.Action import Action
from geniusweb.actions.PartyId import PartyId
from geniusweb.events.ProtocolEvent import ProtocolEvent
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.progress.ProgressFactory import ProgressFactory
from geniusweb.protocol.CurrentNegoState import CurrentNegoState
from geniusweb.protocol.NegoState import NegoState
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.partyconnection.ProtocolToPartyConn import ProtocolToPartyConn
from geniusweb.protocol.partyconnection.ProtocolToPartyConnFactory import ProtocolToPartyConnFactory
from geniusweb.protocol.partyconnection.ProtocolToPartyConnections import ProtocolToPartyConnections
from geniusweb.protocol.session.SessionProtocol import SessionProtocol
from geniusweb.protocol.session.SessionState import SessionState
from geniusweb.protocol.session.saop.SAOPState import SAOPState
from geniusweb.references.PartyWithProfile import PartyWithProfile
from geniusweb.references.ProtocolRef import ProtocolRef
from geniusweb.references.Reference import Reference
from geniusweb.utils import val


class SAOP (DefaultListenable[ProtocolEvent], SessionProtocol):
	'''
	The protocol runs as follows
	<ol>
	<li>The protocol tries to start all parties. If not all parties start, the
	parties are freed up and another attempt is done to start all parties some
	time later.
	<li>All parties are sent the {@link SessionSettings}. Only parties specified 
	initially in the settings do participate. 
	<li>The session deadline clock now starts ticking.
	<li>All parties are sent their settings.
	<li>All parties get YourTurn in clockwise order. A party must do exactly one
	action after it received YourTurn.
	<li>The negotiation continues until an agreement is reached (all parties
	agreed to the last bid), the {@link Deadline} is reached, or a party fails to
	adhere to the protocol.
	<li>If the session times out, the connections are cut and the negotiation
	completes without errors and without agreement.
	</ol>
	<p>
	This logs to "Protocol" logger if there are issues
	<p>
	This object is mutable: the internal state changes as parties interact with
	the protocol.
	<p>
	Thread safe: all entry points are synchronized.
	'''
	_TIME_MARGIN = 20; # ms extra delay after deadline
	_MINDURATION = 100;
	_MIN_SLEEP_TIME = 1000;
	_MAX_SLEEP_TIME = 60000;
	_SAOP = ProtocolRef(URI("SAOP"))

	_isFinishedInfoSent = False 
	_deadlinetimer:Optional[Timer] = None
	_synclock = threading.RLock()

	def __init__(self, state:SAOPState , logger:Reporter ,
			connects:ProtocolToPartyConnections=ProtocolToPartyConnections([]) ) :
		'''
		@param state  normally the initial state coming from SAOPSettings
		@param logger the Reporter to log to
		@param connects the connections to the parties. Defaults to no-connections.
		'''
		super().__init__()
		if state == None:
			raise ValueError("state must be not null")

		if state.getSettings().getDeadline().getDuration() < self._MINDURATION :
			raise ValueError("Duration must be at least " + str(self._MINDURATION))

		self._log = logger
		self._state = state
		self._conns = connects

	def start(self, connectionfactory:ProtocolToPartyConnFactory ):
		with self._synclock: 
			try:
				self._connect(connectionfactory)
				self._setDeadline()
				self._setupParties()
				self._nextTurn()
			except Exception as e:
				traceback.print_exc() #for debugging. 
				self._handleError("Failed to start up session", None, e)

	def getDescription(self)->str:
		return "All parties get YourTurn in clockwise order, after which they can do their next action. "\
				+ "No new participants after start. End after prescribed deadline or when some bid is unanimously Accepted."\
				+ "Parties can only act on their own behalf and only when it is their turn."

	def addParticipant(self, party:PartyWithProfile ):
		raise ValueError("Dynamic joining a negotiation is not allowed in SAOP")

	def getState(self)-> SessionState :
		return self._state

	def getRef(self)->ProtocolRef :
		return self._SAOP

	#*******************************************************************
	# private functions. Some are protected only, for testing purposes
	# ******************************************************************

	def _connect(self, connectionfactory:ProtocolToPartyConnFactory):
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
			participants = self._state.getSettings().getAllParties();
			parties:List[Reference] = [party.getParty().getPartyRef() for party in participants ]
			connections:Optional[List[ProtocolToPartyConn] ] = None
			self._log.log(logging.INFO, "SAOP connect " + str(parties));
			while not connections:
				try:
					connections = connectionfactory.connectAll(parties)
				except NoResourcesNowException as e:
					waitms = (e.getLater().timestamp() - time.time())*1000
					self._log.log(logging.INFO,
							"No resources available to run session, waiting"+ str(waitms))
					time.sleep(min(self._MAX_SLEEP_TIME,
								max(self._MIN_SLEEP_TIME, waitms)))

			for i in range(len(participants)):
				# now we bookkeep the connections ourselves,
				# and update the state to keep in sync.
				self._conns = self._conns.With(connections[i])
				self._setState(self._state.WithParty(connections[i].getParty(),
						participants[i]))

	def _setDeadline(self):
		'''
		Set state to proper deadline. Starts the timer tasks. This tasks triggers
		a call to handleError when the session times out.
		'''
		with self._synclock:
			now = time.time()
			deadline = self._state.getSettings().getDeadline()
			self._setState(self._state.WithProgress(ProgressFactory.create(deadline, 1000*now)))
			
			# set timer TIME_MARGIN after real deadline to ensure we're not too early
			duration=(deadline.getDuration() + self._TIME_MARGIN)/1000.0
			self._deadlinetimer = Timer( duration, self._timertask)
			self._deadlinetimer.start()
			self._log.log(logging.INFO, "SAOP deadline set to "
					+ datetime.utcfromtimestamp(duration+now).strftime('%Y/%m/%d %H:%M:%S'))

	def _timertask(self):
		if not self._state.isFinal(1000.*time.time()):
			self._log.log(logging.CRITICAL,
					"BUG. Deadline timer has triggered but state is not final")
		self._log.log(logging.INFO,
				"SAOP deadline reached. Terminating session.")
		self._finish()
		

	def _setupParties(self) :
		'''
		step 2 in protocol: listen to connections and send settings to the
		parties.
		<p>
		This is 'protected' to allow junit testing, this code is not a 'public'
		part of the interface.
		
		@throws ProtocolException if a party does not follow the protocol
		'''
		this=self
		class MyListener(Listener[Action]):
			def __init__(self, conn):
				self.conn=conn
			def notifyChange(self, action: Action):
				this._actionRequest(self.conn,action)

		with self._synclock:
			for conn in  self._conns:
				conn.addListener(MyListener(conn))
	
			for connection in self._conns:
				try :
					self._sendSettings(connection)
				except ConnectionError as e:
					raise ProtocolException("Failed to initialize",
							connection.getParty(), e)
	

	def _sendSettings(self, connection:ProtocolToPartyConn):
		'''
		Inform a party about its settings
		
		@param connection
		@throws ConnectionError if party got disconnected
		'''
		with self._synclock:
			partyid = connection.getParty()
			profile = self._state.getPartyProfiles()[partyid].getProfile()
			params = self._state.getPartyProfiles()[partyid].getParty()\
					.getParameters();
			if not profile:
				raise ValueError(
						"Missing profile for party " + str(connection.getReference()))
			connection.send(Settings(connection.getParty(), profile, self.getRef(),
					val(self._state.getProgress()), params))

	def   _actionRequest(self, partyconn:ProtocolToPartyConn , action:Action): 
		'''
		This is called when one of the party connections does an action.
		Synchronized so that we always handle only 1 action at a time.
		
		@param partyconn the connection on which the action came in.
		@param action    the {@link Action} taken by some party
		'''
		with self._synclock:
			if not action:
				err = partyconn.getError();
				if not err:
					err = ProtocolException("Party sent a null action",
							partyconn.getParty())
				self._handleError(str(partyconn) + "Protocol error", partyconn.getParty(),
						err)
				return
	
			try:
				if partyconn.getParty() != self._state._getNextActor() :
					# party does not have the turn.
					raise ProtocolException(
							"Party acts without having the turn",
							partyconn.getParty());

				# FIXME? this ignores possible broadcast errors
				self._conns.broadcast(ActionDone(action))
				self._setState(self._state.WithAction(partyconn.getParty(), action))
				if not self._state.isFinal(int(1000*time.time())):
					self._nextTurn()
			except Exception as  e:
				self._handleError("failed to handle action " + str(action),
						partyconn.getParty(), e)


	def _nextTurn(self):
		'''
		Signal next participant it's his turn
		
		
		@throws IOException
		'''
		with self._synclock:
			party = self._state._getNextActor()
			try:
				self._conns.get(party).send(YourTurn())
			except ConnectionError as e:
				self._handleError("failed to send YourTurn", party, e)

	def _handleError(self, message:str, party:Optional[PartyId], e:Exception):
		'''
		Update state to include the given error and finishes up the session.
		
		@param message The message to attach to the error
		@param party   the party where the error occured
		@param e       the exception that occured.
		'''
		with self._synclock:
			if isinstance(e,  ProtocolException):
				self._setState(self._state.WithException( e))
			else:
				self._setState(self._state.WithException(ProtocolException(message, party, e)))
			if party:
				self._setState(self._state.WithoutParty(party))
			self._log.log(logging.WARNING, "SAOP protocol intercepted error due to party "\
					+ str(party) + ":" + message, e)

	def _setState(self, newstate:SAOPState) :
		'''
		Sets the new state. If the new state is final, the finish-up procedure is
		executed.
		
		@param newstate the new state.
		'''
		with self._synclock:
			now = int(1000*time.time())
			if self._state.isFinal(now):
				self._finish()
				return
			self._state = newstate;
			if newstate.isFinal(now):
				self._finish()

	def _finish(self):
		'''
		Called when we reach final state. Cancels deadline timer. Send finished
		info to all parties, notify current nego state as final and set
		{@link #isFinishedInfoSent}. Double calls are automatically ignored.
		'''
		with self._synclock:
			if self._deadlinetimer :
				self._deadlinetimer.cancel()
				self._deadlinetimer = None
			if self._isFinishedInfoSent:
				return;
			self._isFinishedInfoSent=True
			finished = Finished(self._state.getAgreements());
			for conn in self._conns:
				self._sendFinish(conn, finished)
			self.notifyListeners(CurrentNegoState(self._state))

	def _sendFinish(self, connection:ProtocolToPartyConn , finished:Inform ):
		try:
			connection.send(finished)
			connection.close()
		except Exception as e:
			self._log.log(logging.INFO, "Failed to send Finished to " + str(connection), e)

