from os import makedirs
import tempfile
from typing import Union
from uuid import UUID, uuid4

from pyson.JsonValue import JsonValue

import os.path as path

NoneType = type(None)

class FileLocation :
	'''
	This contains a "system independent" {@link File}. This is represented by a
	{@link UUID}. See {@link #getFile()} to get the file referenced by this. The
	file may or may not yet exist (depending on whether your party already wrote
	some contents in that file in previous runs), may or may not be empty (your
	choice), and can contain any type of data. The original intent of this is
	that parties can store learned data in this file, while the name can be kept
	for later re-use in later runs (eg negotiation sessions) on the same machine.
	<p>
	This file is to be used locally on some other machine (typically a
	partiesserver). This object itself only contains a file name.
	{@link #getFile()} turns it into a system-specific {@link File}. <br>
	<h2>WARNING</h2> if used multiple times on different machines, multiple,
	separate files will be involved, there is no magical synchronization of
	multiple items with the same UUID used on different machines.
	'''

	_TMP = tempfile.gettempdir()
	_GENIUSWEBPYTHON = "geniuswebpython";
	_rootpath = path.join(_TMP, _GENIUSWEBPYTHON)

	def __init__(self, name: Union[UUID,NoneType]=None ):
		'''
		@param name the name of the file (must be UUID to prevent injection of
		            bad filenames like /.. or C:) Use {@link #FileLocation()} to
		            create new FileLocation. That should ensure a new UUID that
		            does not collide with existing ones. If None, then this
		            creates a new random UUID.
		'''
		if not path.exists(self._rootpath) :
			makedirs(self._rootpath);
			# don't print the location, python parties would  crash
		if name==None:
			name=uuid4()
		self._name:UUID = name #type:ignore

	@JsonValue()
	def getName(self) -> UUID:
		return self._name

	def getFile(self) ->str :
		'''
		@return Actual filename that can be used for read/write operations. This file
		        usually resides in the geniuswebpython folder inside the tmpdir.
		        This temp dir depends on the run configuration,
		        eg some directory inside the user's home directory, or a temp
		        folder inside tomcat.
		'''
		return path.join(self._rootpath, str(self._name))

	def __repr__(self):
		return "FileLocation[" + self._name + "]"

	def __hash__(self):
		return hash(self._name)

	
	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			self._name==other._name

