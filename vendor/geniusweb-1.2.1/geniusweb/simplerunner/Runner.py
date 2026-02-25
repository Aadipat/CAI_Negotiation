import json
import logging
from pathlib import Path
import sys
import time
import traceback
from typing import List, Optional

from pyson.ObjectMapper import ObjectMapper
from tudelft.utilities.listener.Listener import Listener
from tudelft_utilities_logging.Reporter import Reporter

from geniusweb.events.ProtocolEvent import ProtocolEvent
from geniusweb.protocol.CurrentNegoState import CurrentNegoState
from geniusweb.protocol.NegoProtocol import NegoProtocol
from geniusweb.protocol.NegoSettings import NegoSettings
from geniusweb.protocol.NegoState import NegoState
from geniusweb.simplerunner.ClassPathConnectionFactory import ClassPathConnectionFactory


class Runner:
	'''
	A simple tool to run a negotiation stand-alone, without starting the servers.
	All referred files and classes need to be stored locally (or be in the
	dependency list if you use maven).
	<p>
	<em>IMPORTANT</em> SimpleRunner has a number of restrictions, compared to a
	run using a runserver and partyserver
	<ul>
	<li>With stand-alone runner, your parties are run together in a single
	classloader. The main implication is that there may arise version conflicts
	between parties.
	<li>Stand-alone runner does NOT enforce the time deadline. Parties may
	continue running indefinitely and thus bog down the JVM and stalling
	tournaments.
	</ul>
	'''

	_properlyStopped:bool = False
	_LOOPTIME = 200  # ms
	_FINALWAITTIME = 5000  # ms

	def __init__(self, settings:NegoSettings ,
			connectionfactory:ClassPathConnectionFactory , logger:Reporter ,
			maxruntime:int):
		'''
		@param settings          the {@link NegoSettings}
		@param connectionfactory the {@link ProtocolToPartyConnFactory}
		@param logger            the {@link Reporter} to log problems
		@param maxruntime        limit in millisecs. Ignored if 0
		'''
		if settings == None  or connectionfactory == None:
			raise ValueError("Arguments must be not null");
		self._settings = settings;
		self._log = logger;
		self._protocol = settings.getProtocol(self._log);
		self._connectionfactory = connectionfactory;
		self._maxruntime = maxruntime;
		self._jackson = ObjectMapper()

	def isProperlyStopped(self) -> bool:
		'''
		@return true if the runner has finished
		'''
		return self._properlyStopped

	def run(self):
		this = self

		class protocolListener(Listener[ProtocolEvent]):

			def notifyChange(self, evt: ProtocolEvent):
				this._handle(evt)

		self._protocol.addListener(protocolListener())
		self._protocol.start(self._connectionfactory)
		remainingtime = self._maxruntime;
		while not self._properlyStopped and  (self._maxruntime == 0 or remainingtime > 0):
			time.sleep(self._LOOPTIME / 1000.)
			remainingtime -= self._LOOPTIME
		self._log.log(logging.INFO, "Waiting for connection closure")

		remainingtime = self._FINALWAITTIME;
		while remainingtime > 0 and\
			len(self._connectionfactory.getOpenConnections()) != 0:
				time.sleep(self._LOOPTIME / 1000.)
				remainingtime -= self._LOOPTIME
			
		openconn = self._connectionfactory.getOpenConnections()
		if len(openconn) != 0:
			self._log.log(logging.WARNING, "Connections " + str(openconn)\
					+" did not close properly at end of run")
		self._log.log(logging.INFO, "end run")

	def _handle(self, evt:ProtocolEvent):
		if isinstance(evt , CurrentNegoState) and \
			evt.getState().isFinal(1000 * time.time()):
				self._stop()

	def _stop(self):
		self._logFinal(logging.INFO, self._protocol.getState())
		self._properlyStopped = True

	def _logFinal(self, level:int , state: NegoState):
		'''
		Separate so that we can intercept this when mocking, as this will crash
		on mocks because {@link #jackson} can not handle mocks.
		
		@param level the log {@link Level}, eg logging.WARNING
		@param state the {@link NegoState} to log
		'''
		try:
			self._log.log(level, "protocol ended normally: "
					+json.dumps(self._jackson.toJson(self._protocol.getState())))
		except Exception as e:  # catch json issues
			traceback.print_exc()

	def getProtocol(self) -> NegoProtocol:
		'''
		@return protocol that runs/ran the session.
		'''
		return self._protocol
