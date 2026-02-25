import logging
import sys
from typing import List, Optional

from PyQt5 import QtCore
from PyQt5.QtWidgets import QWidget, QTextEdit, QGridLayout, QPushButton, \
	QApplication, QMainWindow
from tudelft_utilities_logging.Reporter import Reporter

from geniusweb.simplerunner.ClassPathConnectionFactory import ClassPathConnectionFactory
from geniusweb.simplerunner.Runner import Runner
from geniusweb.simplerunner.gui.SettingsPanel import SettingsPanel


class GUI (QWidget):
	'''
	Simple GUI allowing users to create the settings interactively, much like on
	the runserver
	'''
	# dataChannel needed to pipe output text from the runner
	# into the PyQt system
	dataChannel = QtCore.pyqtSignal(str)

	def __init__(self):
		super().__init__()
		self.dataChannel.connect(self.receive)
		self.resultarea = QTextEdit()
		self.resultarea.setReadOnly(True)
		self.resultarea.setText("Results will appear here after run")
		# set dimension , 9, 40

		layout = QGridLayout()
		self.setLayout(layout)
	
		self.settingsPanel = SettingsPanel()
		layout.addWidget(self.settingsPanel)
		layout.addWidget(self.startPanel())

	def startPanel(self) -> QWidget:
		startpanel = QWidget()
		layout = QGridLayout()
		startpanel.setLayout(layout)
		
		startbutton = QPushButton()
		startbutton.setText("Start Session")
		layout.addWidget(startbutton)
		layout.addWidget(self.resultarea)

		this = self
		startbutton.clicked.connect(this.runsession)  # type:ignore
		return startpanel;

	def runsession(self, b):
		self.resultarea.setText("")
		this = self
		
		class MyReporter(Reporter):

			# override
			def log(self, level:int, msg:str, thrown:Optional[BaseException]=None):
				text = "[" + logging._levelToName[level] + "] " + msg + "\n"
				# in python you can not turn a exception into a string
				if thrown:
					text = text + str(thrown) + "\n"
				this.dataChannel.emit(text)

		myreporter = MyReporter() 
		runner = Runner(self.settingsPanel.getSettings(),
			ClassPathConnectionFactory(), myreporter, 0)
		runner.run()

	def receive(self, text:str):
		self.resultarea.append(text)

	@staticmethod
	def main(args:List[str]):
		app = QApplication([])
		
		win = QMainWindow()
		win.setWindowTitle("GeniusWeb SimpleRunner GUI")
		win.setCentralWidget(GUI())
		win.show()
		sys.exit(app.exec_())


if __name__ == '__main__':
	GUI.main([])
