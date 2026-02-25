import json
import traceback

from PyQt5.QtWidgets import QWidget, QGridLayout, QLabel, QComboBox, QSpinBox, \
	QFrame, QSplitter, QLineEdit, QPushButton, QTableView, QScrollArea, QVBoxLayout, \
	QTextEdit, QMessageBox
from pyson.ObjectMapper import ObjectMapper
from uri.uri import URI

from geniusweb.deadline.Deadline import Deadline
from geniusweb.deadline.DeadlineRounds import DeadlineRounds
from geniusweb.deadline.DeadlineTime import DeadlineTime
from geniusweb.protocol.NegoSettings import NegoSettings
from geniusweb.protocol.session.TeamInfo import TeamInfo
from geniusweb.protocol.session.saop.SAOPSettings import SAOPSettings
from geniusweb.references.Parameters import Parameters
from geniusweb.references.PartyRef import PartyRef
from geniusweb.references.PartyWithParameters import PartyWithParameters
from geniusweb.references.PartyWithProfile import PartyWithProfile
from geniusweb.references.ProfileRef import ProfileRef
from geniusweb.simplerunner.gui.MyFileChooser import MyFileChooser
from geniusweb.simplerunner.gui.SelectionModel import SelectionModel


class SettingsPanel(QWidget):
	
	def __init__(self):
		super().__init__()
		self.jackson = ObjectMapper()
		self.protocolcombo = QComboBox()
		self.protocolcombo.addItems([ "SAOP" ])
		self.timepanel = TimePanel()
		self.nextparty = QLineEdit()
		self.nextparameters = QLineEdit()
		
		self.nextprofile = MyFileChooser()
		self.addButton = QPushButton()
		self.addButton.setText("add")
		self.selectedparties = SelectionModel()

		layout = QGridLayout()
		self.setLayout(layout)
		
		layout.addWidget(WithLabel("protocol", self.protocolcombo))
		layout.addWidget(WithLabel("deadline", self.timepanel))
		layout.addWidget(Separator())
		
		partic = QLabel()
		partic.setText("participants")
		layout.addWidget(partic)
		
		layout.addWidget(WithLabel("party:", self.nextparty))
		layout.addWidget(WithLabel("parameters:", self.nextparameters))
		layout.addWidget(WithLabel("profile:", self.nextprofile))
		
		layout.addWidget(Separator())

		layout.addWidget(self.addButton)
		
		label = QLabel()
		label.setText("Selected Profiles, parties for the session")
		layout.addWidget(label)
		
		table = QTableView()
		table.setModel(self.selectedparties)
		layout.addWidget(table)
		self.addButton.clicked.connect(self.addparty);

	def addparty(self):
		try:
			self.addparty1()
		except ValueError as e:
			traceback.print_exc()
			mbox = QMessageBox()
			mbox.setText(str(e))
			mbox.setWindowTitle("Failed to add party")
			mbox.setIcon(QMessageBox.Icon.Warning)
			mbox.exec_()
 
	def addparty1(self):
		try:
			partyref = PartyRef(URI("pythonpath:" + self.nextparty.text()))
		except Exception as e:
			raise ValueError("Party not set correctly:" + str(e))

		try:
			parameters = self.jackson.parse(json.loads("{" + self.nextparameters.text() + "}"),
					Parameters)
		except Exception as e:
			raise ValueError("Parameters not set correctly:" + str(e))

		try:
			profile = ProfileRef(URI("file:" + self.nextprofile.getFile()))
		except Exception as  e:
			raise ValueError("Profile not set correctly:" + str(e))

		partywithparams = PartyWithParameters(partyref, 	parameters);
		partywithprofile = PartyWithProfile(partywithparams, profile);
		teaminfo = TeamInfo([partywithprofile])
		self.selectedparties.addTeam(teaminfo)
 
	def getSettings(self) -> NegoSettings:
		return SAOPSettings(self.selectedparties.getTeams(),
				self.timepanel.getDeadline())


class WithLabel (QWidget):
	'''
	adds label to left of component
	'''

	def __init__(self, label:str, component:QWidget):
		super().__init__()
		layout = QGridLayout()
		self.setLayout(layout)
		
		qlabel = QLabel()
		qlabel.setText(label)

		layout.addWidget(qlabel, 0, 0)
		layout.addWidget(component, 0, 1)


class TimePanel(QWidget):
	DEFAULTDEADLINE = 10000  # millisecs
	
	def __init__(self):
		super().__init__()
		self.unitcombo = QComboBox()
		self.unitcombo.addItems(["seconds", "rounds"])
		self.time = QSpinBox()
		self.time.setMinimum(1)
		self.time.setMaximum(1000)
		self.time.setValue(10)

		layout = QGridLayout()
		self.setLayout(layout)

		layout.addWidget(self.time, 0, 0)
		layout.addWidget(self.unitcombo, 0, 1)

	def getDeadline(self) -> Deadline:
		if self.unitcombo.currentIndex() == 0:  # time
			return DeadlineTime(self.time.value() * 1000);
		return DeadlineRounds(self.time.value(), self.DEFAULTDEADLINE)


class Separator(QFrame):
	'''
	Equivalent of java's JSeparator: just a horizontal line for layout
	'''
	
	def __init__(self):
		super().__init__()
		self.setFrameShape(QFrame.Shape.HLine)
		self.setFrameShadow(QFrame.Shadow.Sunken)
	
