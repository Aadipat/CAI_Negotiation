from PyQt5.QtWidgets import QWidgetAction, QTextEdit, QPushButton, QGridLayout, \
	QFileDialog, QWidget, QLineEdit


class MyFileChooser (QWidget):
	'''
	one-line panel with on left the chosen file and on the right a "Browse"
	button. If you click browse button you can browse for a file. You can also
	just type the file location.
	'''

	def __init__(self):
		super().__init__()
		self.filenamearea = QLineEdit()
		self.filenamearea.setText("select a file")
		self.browsebutton = QPushButton()
		self.browsebutton.setText("Browse")

		layout = QGridLayout()
		self.setLayout(layout)

		layout.addWidget(self.filenamearea, 0, 0)
		layout.addWidget(self.browsebutton, 0, 1)
		self.browsebutton.clicked.connect(self.browseclick)

	def browseclick(self):
				fc = QFileDialog()
				if fc.exec_() > 0:  # ? what does this function return?
					self.filenamearea.setText(fc.selectedFiles()[0])

	def getFile(self) -> str:
		return self.filenamearea.text();
