from datetime import datetime
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
from geniusweb.actions.PartyId import PartyId
from geniusweb.events.ProtocolEvent import ProtocolEvent
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.progress.ProgressFactory import ProgressFactory
from geniusweb.protocol.CurrentNegoState import CurrentNegoState
from geniusweb.protocol.NegoState import NegoState
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.partyconnection.ProtocolToPartyConn import ProtocolToPartyConn
from geniusweb.protocol.partyconnection.ProtocolToPartyConnFactory import ProtocolToPartyConnFactory
from geniusweb.protocol.partyconnection.ProtocolToPartyConnections import ProtocolToPartyConnections
from geniusweb.protocol.session.SessionProtocol import SessionProtocol
from geniusweb.protocol.session.learn.LearnState import LearnState
from geniusweb.references.PartyWithProfile import PartyWithProfile
from geniusweb.references.ProtocolRef import ProtocolRef
from geniusweb.utils import val


MIN_SLEEP_TIME = 1000
MAX_SLEEP_TIME = 60000
TIME_MARGIN = 20 # ms extra delay after deadline
LEARN = ProtocolRef(URI("Learn"))
	 
class Learn (DefaultListenable[ProtocolEvent],SessionProtocol):
	'''
	The Learn protocol allows parties to learn until the deadline set in the
	{@link LearnSettings}.
	'''
	_deadlinetimer:Optional[Timer] = None
# 	private volatile AtomicBoolean isFinishedInfoSent = new AtomicBoolean(
# 			false);
	_conns = ProtocolToPartyConnections([])
	_synclock = threading.RLock()
	_isFinishedInfoSent = False 

	def __init__(self, state:LearnState, logger:Reporter ):
		super().__init__()
		self._state = state
		self._log = logger

	def start(self, connectionfactory:ProtocolToPartyConnFactory ):
		try:
			self._connect(connectionfactory)
			self._setDeadline()
			self._setupParties()
		except Exception as e:
			self._handleError("Failed to start up session", None, e)

	def getDescription(self)->str:
		return "Sends all parties the Settings. Parties can start learning immediately but must respect the deadline. When party is done, it should send LearningDone."

	def getState(self)->NegoState :
		return self._state


	def getRef(self)-> ProtocolRef:
		return LEARN

	def addParticipant(self, party:PartyWithProfile ) :
		raise ValueError(
				"Dynamic joining a negotiation is not allowed in LEARN")

	#####################################################################
	# private functions. Some are protected only, for testing purposes
	#####################################################################
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
		
		@throws IOException  if this fails to properly conect to the
                             parties, eg interrupted or server not
                             responding..
		'''
		with self._synclock:
			participants:List[PartyWithProfile] = self._state.getSettings().getAllParties()
			
			parties = [parti.getParty().getPartyRef() for parti in participants ]
			connections:Optional[List[ProtocolToPartyConn]]  = None
			self._log.log(logging.INFO, "LEARN connect " + str(parties))
			while connections == None:
				try:
					connections = connectionfactory.connectAll(parties) # type:ignore
				except NoResourcesNowException as e:
					waitms = (e.getLater().timestamp()-time())*1000
					self._log.log(logging.INFO,
							"No resources available to run session, waiting"+ str(waitms))
					sleep(min(MAX_SLEEP_TIME,
							max(MIN_SLEEP_TIME, waitms))/1000)
			# need val because mypy fails to see that connections can't be None here.
			for i  in range(len(participants)):
				self._conns = self._conns.With(val(connections)[i])
				self._setState(self._state.WithParty(val(connections)[i].getParty(),
						participants[i]))

	def  _actionRequest(self, partyconn:ProtocolToPartyConn , action:Action ) :
		'''
		This is called when one of the party connections does an action.
		Synchronized so that we always handle only 1 action at a time.
		
		@param partyconn the connection on which the action came in.
		@param action    the {@link Action} taken by some party
		'''	
		with self._synclock:
			if action == None:
				err = partyconn.getError()
				if err == None:
					err = ProtocolException("Party sent a null action",
							partyconn.getParty())
				self._handleError(str(partyconn) + "Protocol error", partyconn.getParty(),
						err) #type:ignore
				return
	
			try:
				self._setState(self._state.WithAction(partyconn.getParty(), action))
			except Exception as  e:
				self._handleError("failed to handle action " + str(action),
						partyconn.getParty(), e)




	def _setupParties(self):
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
			def notifyChange(self, act:Action):
				this._actionRequest(act)

		
		with self._synclock:

			for conn in self._conns:
				conn.addListener(MyListener())
	
			for connection in self._conns:
				try:
					self._sendSettings(connection)
				except ConnectionError as e:
					raise ProtocolException("Failed to initialize",
							connection.getParty(), e)


	def _sendSettings(self, connection:ProtocolToPartyConn ):
		'''
		Inform a party about its settings
		
		@param connection
		@throws IOException if party got disconnected
		'''
		with self._synclock:
			partyid = connection.getParty()
			profile = self._state.getPartyProfiles()[partyid].getProfile()
			params = self._state.getPartyProfiles()[partyid].getParty().getParameters()
			if profile == None:
				raise ValueError(
						"Missing profile for party " + str(connection.getReference()))
			connection.send(Settings(connection.getParty(), profile, self.getRef(),
					val(self._state.getProgress()), params))

	def _setDeadline(self):
		'''
		Set state to proper deadline. Starts the timer tasks. This tasks triggers
		a call to handleError when the session times out.
		'''
		with self._synclock:
			now = int(time()*1000)
			deadline = self._state.getSettings().getDeadline()
			self._setState(self._state.WithProgress(ProgressFactory.create(deadline, now)))
			duration=(deadline.getDuration() + TIME_MARGIN)/1000.0
			self._deadlinetimer = Timer(duration, self._timertask);

			# set timer TIME_MARGIN after real deadline to ensure we're not too early
			duration=(deadline.getDuration() + TIME_MARGIN)/1000.0
			self._deadlinetimer = Timer( duration, self._timertask)
			self._deadlinetimer.start()
			self._log.log(logging.INFO, "SAOP deadline set to "
					+ datetime.utcfromtimestamp( (duration+now)/1000. ).strftime('%Y/%m/%d %H:%M:%S'))

	def _timertask(self):
		if not self._state.isFinal(1000.*time()):
			self._log.log(logging.CRITICAL,
					"BUG. Deadline timer has triggered but state is not final")
		self._log.log(logging.INFO,
				"LEARN deadline reached. Terminating session.")
		self._finish()


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
			self._log.log(logging.WARNING, "LEARN protocol intercepted error due to party "\
					+ str(party) + ":" + message, e)

	def _setState(self, newstate:LearnState) :
		'''
		Sets the new state. If the new state is final, the finish-up procedure is
		executed.
		
		@param newstate the new state.
		'''
		with self._synclock:
			now = int(1000*time())
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


