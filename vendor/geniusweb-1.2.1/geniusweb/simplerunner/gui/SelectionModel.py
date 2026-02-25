from typing import List

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QVariant
from PyQt5.QtCore import Qt

from geniusweb.protocol.session.TeamInfo import TeamInfo
from geniusweb.references.PartyWithProfile import PartyWithProfile


class SelectionModel(QAbstractTableModel):
	'''
	The selected parties, profiles etc
	'''

	colnames = ["Party", "Parameters", "Profile"]

	def __init__(self):
		super().__init__()
		self._teams:List[TeamInfo] = []
		# pyqt does not use listeners

	def getTeams(self) -> List[TeamInfo]:
		return self._teams

	def addTeam(self, team:TeamInfo):
		self._teams.append(team)
		self.beginResetModel()
		self.endResetModel()

	# Override
	def rowCount(self, parent=QModelIndex()):
		return len(self._teams) 

	# Override
	def columnCount(self, parent=QModelIndex()):
		return 3 

	def data(self, index, role=None):
		if role == Qt.ItemDataRole.DisplayRole:
			party:PartyWithProfile = self._teams[index.row()].getParties()[0]
			if index.column() == 0:
				return str(party.getParty().getPartyRef().getURI())
			if index.column() == 1:
				return str(party.getParty().getParameters())
			if index.column() == 2:
				return str(party.getProfile().getURI())
			return "???"
		return None  # without this you get checkboxes everywhere in table...

	def headerData(self, column:int, orientation, role=Qt.ItemDataRole.DisplayRole):
		if role != Qt.ItemDataRole.DisplayRole:
			return QVariant()
		if orientation == Qt.Orientation.Horizontal:
			return QVariant(self.colnames[column]) 
