from PyQt5 import QtGui, QtWidgets  # Import the PyQt5 module we'll need
import sys  # We need sys so that we can pass argv to QApplication
from PyQt5.QtCore import QUrl, QTimer, Qt, QVariant
#from PyQt5.QtCore import QString
from PyQt5 import QtCore
from PyQt5.QtGui import QFont
from PyQt5.QtWebKit import QWebSettings
from PyQt5.QtWebKitWidgets import QWebPage
from PyQt5.QtWidgets import QAction, QTreeWidgetItem, QMenu, QTabBar
from PyQt5 import QtPrintSupport

import GUI  # This file holds our MainWindow and all design related things
import sqlite3
import pyscrypt
import cStringIO
import base64

# it also keeps events etc that we defined in Qt Designer
import os  # For listing directory methods
import atexit

class UiApp(QtWidgets.QMainWindow, GUI.Ui_MainWindow):
    passwd = ""
    id = None
    old_content = ""

    def __init__(self):
        # Explaining super is out of the scope of this article
        # So please google it if you're not familar with it
        # Simple reason why we use it here is that it allows us to
        # access variables, methods etc in the design.py file
        super(self.__class__, self).__init__()
        self.setupUi(self)  # This is defined in ui file automatically
        self.fillPassword()

        self.conn = sqlite3.connect('nooto.db')
        self.conn.row_factory = sqlite3.Row
        self.curs = self.conn.cursor()
        self.curs.execute('SELECT id,title,parent FROM Note')
        titles = self.curs.fetchall()

        self.id2objmap = {}
        # sort by parent value
        titles = sorted(titles,key=lambda parent: parent['parent'])

        for row in titles:
            if row['parent'] == None:
                title = self.decrypt(row['title'])
                item = QTreeWidgetItem(self.treeWidget)
                item.setText(0,title)
                item.setText(1,str(row['id']))
                self.id2objmap[row['id']] = {'title':title,'parent':None,'object':item}
            else :
                title = self.decrypt(row['title'])
                parent = row['parent']
                item = QTreeWidgetItem(self.id2objmap[parent]['object'])
                item.setText(0,title)
                item.setText(1,str(row['id']))
                item.setText(2,str(parent))
                self.id2objmap[row['id']] = {'title':title,'parent':parent,'object':item}

        self.treeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treeWidget.customContextMenuRequested.connect(self.openContextMenu)
        self.treeWidget.setHeaderLabel("Note Title")
        self.treeWidget.setColumnCount(1)
        self.treeWidget.expandAll()

        settings = QWebSettings.globalSettings()
        settings.setAttribute(QWebSettings.JavascriptCanAccessClipboard,True)
        settings.setAttribute(QWebSettings.PluginsEnabled,True)

        url = QUrl('file://' + os.getcwd() + '/index.html')
        #url = QUrl('http://www.tinymce.com/tryit/full.php')
        self.webView.setUrl(url)
        #self.webView.page().setContentEditable(True)
        self.webView.page().mainFrame().addToJavaScriptWindowObject("pyObj", self)

        self.treeWidget.itemClicked.connect(self.getTreeItemText)

    @QtCore.pyqtSlot(str)
    def message_test(self,content):
        print "from javascript "+content

    def openContextMenu(self, position):
        menu = QMenu()
        add_note = QAction("add note",self)
        add_subnote = QAction("add sub note",self)
        delete_note = QAction("delete note",self)
        add_note.triggered.connect(self.addNote)
        add_subnote.triggered.connect(self.addSubNote)
        delete_note.triggered.connect(self.deleteNote)
        menu.addAction(add_note)
        menu.addAction(add_subnote)
        menu.addAction(delete_note)
        menu.exec_(self.treeWidget.viewport().mapToGlobal(position))

    def fillPassword(self):
        passwd, ok = QtWidgets.QInputDialog.getText(self, 'Input Password', 'Enter your password:',echo=QtWidgets.QLineEdit.Password)
        if ok and not (len(passwd) == 0):
            self.passwd = str(passwd)
        else:
            sys.exit(1)

    def getTreeItemText(self):
        self.id = int(str(self.treeWidget.currentItem().text(1)))
        param = (self.id,)
        self.curs.execute('SELECT content FROM Note WHERE id=?', param)
        row = self.curs.fetchone()
        content = self.decrypt(row['content'])
        self.setHTML(content=content)

    @QtCore.pyqtSlot(str)
    def saveNote(self,content):
        print "saving"
        param = (self.encrypt(content), self.id,)
        self.curs.execute('UPDATE Note SET content=? where id=?', param)
        self.conn.commit()
        print "saved"

    def setHTML(self, _=None, content=''):
        frame = self.webView.page().mainFrame()
        web_frame = frame.evaluateJavaScript("updateContent(\"{0}\")".format(content))

    def addNote(self):
        title, ok = QtWidgets.QInputDialog.getText(self, 'New Note', 'Enter new title:')
        if ok:
            param = (self.encrypt(content=str(title)), self.encrypt(content=""),None,)
            self.curs.execute('INSERT INTO Note (title,content,parent) VALUES (?,?,?)', param)
            self.conn.commit()
            item = QTreeWidgetItem(self.treeWidget)
            item.setText(0,title)
            id = self.curs.lastrowid
            item.setText(1,str(id))
            self.id2objmap[id] = {'title':str(title),'parent':None,'object':item}

    def addSubNote(self):
        title, ok = QtWidgets.QInputDialog.getText(self, 'New Note', 'Enter new title:')
        if ok:
            try:
                # get parent id
                parent_id = int(str(self.treeWidget.currentItem().text(1)))
                param = (self.encrypt(content=str(title)), self.encrypt(content=""), parent_id,)
                self.curs.execute('INSERT INTO Note (title,content,parent) VALUES (?,?,?)', param)
                item = QTreeWidgetItem(self.treeWidget.currentItem())
                item.setText(0,title)
                id = self.curs.lastrowid
                item.setText(1,str(id))
                item.setText(2,str(parent_id))
            except:
                print "error creating sub note"
            finally:
                self.conn.commit()
                self.id2objmap[id] = {'title':str(title),'parent':parent_id,'object':item}
                self.treeWidget.currentItem().setExpanded(True)

    def deleteNote(self):
        reply = QtWidgets.QMessageBox.question(self, 'Delete Note',
                                           "Are you sure want to delete?", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                           QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            item = self.treeWidget.currentItem()
            self.deleteChild(item)
            id = int(str(item.text(1)))
            param = (id,)
            self.curs.execute('DELETE FROM Note WHERE id=?', param)
            print "remove note = ", self.id2objmap.pop(id)
            (item.parent() or self.treeWidget.invisibleRootItem()).removeChild(item)
            self.conn.commit()
            self.setHTML(content=base64.b64encode("<h1>Content Deleted</h1>"))

    def deleteChild(self,item):
        if item.childCount() != 0:
            for child in item.takeChildren():
                self.deleteChild(child)
                id = int(str(child.text(1)))
                param = (id,)
                self.curs.execute('DELETE FROM Note WHERE id=?', param)
                print "remove note = ", self.id2objmap.pop(id)
        else:
            return

    def encrypt(self, content):
        output = cStringIO.StringIO()
        sf = pyscrypt.ScryptFile(output, self.passwd, 1024, 1, 1)
        sf.write(content)
        sf.finalize()
        encrypted = base64.b64encode(output.getvalue())
        # print "enc = ",encrypted
        output.close()
        return encrypted

    def decrypt(self, content):
        input = cStringIO.StringIO()
        bin_content = base64.b64decode(content)
        input.write(bin_content)
        input.seek(0)
        sf = pyscrypt.ScryptFile(input, password=self.passwd)
        return sf.read()


def main():
    app = QtWidgets.QApplication(sys.argv)
    form = UiApp()
    form.show()
    app.exec_()

if __name__ == '__main__':  # if we're running file directly and not importing it
    main()  # run the main function
