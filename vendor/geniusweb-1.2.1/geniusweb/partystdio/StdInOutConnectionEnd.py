import json
import sys
from typing import Optional

from pyson.ObjectMapper import ObjectMapper
from tudelft.utilities.listener.DefaultListenable import DefaultListenable
from tudelft.utilities.listener.Listener import Listener

from geniusweb.actions.Action import Action
from geniusweb.connection.ConnectionEnd import ConnectionEnd 
from geniusweb.inform.Inform import Inform


class StdInOutConnectionEnd(DefaultListenable[Inform],ConnectionEnd[Inform, Action]):
	'''
	A connectionend for a party that forwards stdin to the party,
	and pushes outdata from the party back into the stream.
	'''
	def __init__(self):
		super().__init__()
		self._pyson = ObjectMapper()

	
	def send(self,act:Action ):
		data=json.dumps(self._pyson.toJson(act))
		sys.stdout.buffer.write(len(data).to_bytes(4,'little'))
		sys.stdout.buffer.write(bytes(data, 'utf-8'))
		sys.stdout.buffer.flush()
	
	def run(self, receiver: Listener[Inform]):
		'''
		@param receiver the listener for the information
		runs until the input breaks.
		returns only after termination 
		@raise exception if the read or the receiver throws: 
		'''
		# blocking read
		while True:
			data=self.readblock()
			if not data: 
				break
			
			obj=self._pyson.parse(json.loads(data.decode("utf-8")),Inform)
			receiver.notifyChange(obj)
		# FIXME receiver.terminate?
		
	def readblock(self)->Optional[bytearray]:
		'''
		@return next block of data from stdin, or None if stream closed.
		'''
		sizedata=sys.stdin.buffer.raw.read(4) #type:ignore
		if len(sizedata)<4:
			return None 
		remaining=int.from_bytes(sizedata, byteorder='little',signed=True)
		if remaining>20000000:
			raise ValueError("Received bad block:"+str(remaining))
		#sys.stderr.write("remaining: "+str(remaining))
		
		data=bytearray()
		while remaining>0:
			newdata=sys.stdin.buffer.raw.read(remaining) #type:ignore
			if len(newdata)==0:
				# FIXME receiver.terminate ?
				return None
			data.extend(bytearray(newdata))
			remaining=remaining-len(newdata)
		return data
	