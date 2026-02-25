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
from geniusweb.simplerunner.Runner import Runner
from geniusweb.simplerunner.gui.GUI import GUI


class StdOutReporter (Reporter):

	def log(self, level:int , msg:str, exc:Optional[BaseException]=None):
		if level >= logging.WARNING:
			print(logging.getLevelName(level) + ":" + msg, file=sys.stderr)
		else:
			print(logging.getLevelName(level) + ":" + msg)


class NegoRunner:
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

	@staticmethod
	def main(args:List[str]):
		'''
		The main runner
		
		@param args should have 0 or 1 argument. If 0 arguments, the {@link GUI}
		            is started. If one argoment, it should be a filename
		            containing a settings.json file. That session is then run.
		@throws IOException if problem occurs
		'''
		if len(args) == 0:
			GUI.main([])
			return 
		
		if len(args) != 1:
			NegoRunner.showusage()
			return;
		
		serialized = Path(args[0]).read_text("utf-8")
		settings:NegoSettings = ObjectMapper().parse(json.loads(serialized),
						NegoSettings)  # type:ignore

		runner = Runner(settings,
				ClassPathConnectionFactory(), StdOutReporter(), 0)
		runner.run()

	@staticmethod
	def showusage():
		print("GeniusWeb stand-alone runner.")
		print("first argument should be <settings.json>.")
		print("The settings.json file should contain the NegoSettings.")
		print("See the settings.json example file and the GeniusWeb wiki pages. ")
	

if __name__ == '__main__': 
	NegoRunner.main(sys.argv[1:])
	
