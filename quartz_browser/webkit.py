# -*- coding: utf-8 -*-
from PyQt5.QtCore import QSettings, QUrl, QByteArray, QTimer, pyqtSignal, QFileInfo, Qt, QThread, QFile, QIODevice, qDebug
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QInputDialog, QLineEdit, QFileDialog, QMenu, QMenu, QAction, QMessageBox, QToolButton
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineView, QWebEngineProfile
from PyQt5.QtWebEngineCore import QWebEngineCookieStore, QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestInfo
from PyQt5.QtNetwork import QNetworkRequest, QNetworkCookie, QNetworkCookieJar, QNetworkAccessManager

from common import *
import os, shlex, subprocess
from urllib import parse
import adblockparser

KIOSK_MODE = False

js_debug_mode = False
enable_adblock = True
block_fonts = False
block_popups = False
find_mode_on = False
useragent_mode = 'Desktop'
useragent_custom = 'Chromium 34.0'
video_player_command = 'ffplay'

blocklist = program_dir + 'easylist.txt'

class RequestInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = adblockparser.AdblockRules(["https://easylist.to/easylist/easylist.txt"])
        file = QFile(blocklist)
        if not file.exists():
            qDebug("No easylist.txt file found.")
            return

        if file.open(QIODevice.ReadOnly | QIODevice.Text):
            easyListTxt = str(file.readAll(), encoding="utf-8")
            self.client = adblockparser.AdblockRules(easyListTxt.splitlines())
        file.close()

    def interceptRequest(self, info: QWebEngineUrlRequestInfo):
        url = info.requestUrl()
        if self.client.should_block(url.toString()):
            info.block(True)

class MyWebPage(QWebEnginePage):
    """Reimplemented  to get User Agent Changing and multiple file uploads facility"""
    def __init__(self, parent):
        QWebEnginePage.__init__(self, parent)
        # self.setForwardUnsupportedContent(True) idk
        # self.setLinkDelegationPolicy(2) idk x2
        
        # self.useragent_desktop = QWebEnginePage.userAgentForUrl(self, QUrl())

    def extension(self, extension, option, output):
        """ Allows to upload files where multiple selections are allowed """
        if extension == QWebEnginePage.ChooseMultipleFilesExtension:
            output.fileNames, sel_filter = QFileDialog.getOpenFileNames(self.view(), "Select Files to Upload", homedir)
            return True
        elif extension == QWebEnginePage.ErrorPageExtension:
            error_dict = {'0':'QtNetwork', '1':'HTTP', '2':'Webkit'}
            print("URL : {}".format(option.url.toString()))
            print("{} Error {} : {}".format(error_dict[str(option.domain)], option.error, option.errorString))
        return False

    def supportsExtension(self, extension):
        return True

    def javaScriptConsoleMessage(self, msg, line_no, source_id):
        global js_debug_mode
        if js_debug_mode:
            print("Line : {} , Source ID - {}".format(line_no, source_id))
            print(msg)

    def shouldInterruptJavaScript(self):
        return True
    
    def acceptNavigationRequest(self, qurl, navtype, mainframe):
        MyWebView.openLink(MyWebView, qurl) # wtf im doing, there is no way that this will work

class MyWebView(QWebEngineView):
    ''' parameters
        @parent -> QTabWidget
    '''
    windowCreated = pyqtSignal(QWebEngineView)
    videoListRequested = pyqtSignal()
    def __init__(self, parent,):
        QWebEngineView.__init__(self, parent)
        self.useragent_desktop = "Mozilla/5.0 (X11; Linux) AppleWebKit/538.1 (KHTML, like Gecko) Quartz Safari/538.1"
        self.useragent_mobile = 'Nokia 5130' #wtf bruh
        interceptor = RequestInterceptor()
        adblockProfile = QWebEngineProfile()
        adblockProfile.setUrlRequestInterceptor(interceptor)
        if useragent_mode == 'Mobile':
            adblockProfile.setHttpUserAgent(self.useragent_mobile)
        elif useragent_mode == 'Custom':
            adblockProfile.setHttpUserAgent(useragent_custom)
        elif useragent_mode == 'Desktop':
            adblockProfile.setHttpUserAgent(self.useragent_desktop)
        adblockProfile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        adblockProfile.setCachePath("Cache")
        adblockProfile.setPersistentStoragePath("Storage")
        page = MyWebPage(adblockProfile) #hmm no self?
        self.setPage(page)
        self.edit_mode_on = False
        self.loading = False
        self.progressVal = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.reload)
        # page.contentsChanged.connect(self.resetTimer) :( https://stackoverflow.com/a/41974756
        self.loadStarted.connect(self.onLoadStart)
        self.loadFinished.connect(self.onLoadFinish)
        self.loadProgress.connect(self.onLoadProgress)
        # self.linkClicked.connect(self.openLink) reimplemented in myWebPage

    def onLoadStart(self):
        self.loading = True

    def onLoadFinish(self):
        self.loading = False

    def onLoadProgress(self, progress):
        self.progressVal = progress
        self.resetTimer()

    def openLink(self, url):
        addr = url.toString()
        # This supports rtsp video play protocol
        if addr.startswith('rtsp://'):
            global video_player_command
            cmd = video_player_command + ' ' + addr
            try:
                subprocess.Popen(shlex.split(cmd))
            except OSError:
                QMessageBox.warning(self, "Command not Found !","The video player command not found.\nGoto Settings > Download & media and change command.")
            return
        self.load(url)

    def createWindow(self, windowtype):
        """This function is internally called when new window is requested.
           This will must return a QWebEngineView object"""
        global block_popups
        if block_popups:
            return None # Replace this by "return self" if want to open new tab in current tab.
        webview = MyWebView(self.parent(), self.page().networkAccessManager())
        self.windowCreated.emit(webview)
        return webview

    def contextMenuEvent(self, event):
        """ Overrides the default context menu"""
        # No context menu in kiosk mode
        if KIOSK_MODE : return
        # Get source code at mouse click pos
        result = self.page().mainFrame().hitTestContent(event.pos())
        element = result.element()
        child = element.firstChild()
        src = ''
        print(element.toOuterXml())
        if element.hasAttribute('src'):
            src = element.attribute('src')
        elif child.hasAttribute('src'):
            src = child.attribute('src')

        self.rel_pos = event.pos()
        menu = QMenu(self)
        if result.isContentSelected():
           copy_text_action = self.pageAction(QWebEnginePage.Copy)
           copy_text_action.setIcon(QIcon(':/edit-copy.png'))
           menu.addAction(copy_text_action)
        if not result.imageUrl().isEmpty():
           menu.addAction(QIcon(':/document-save.png'), "Save Image", self.saveImageToDisk)
           download_image_action = self.pageAction(QWebEnginePage.DownloadImageToDisk)
           download_image_action.setText("Download Image")
           download_image_action.setIcon(QIcon(':/image-x-generic.png'))
           menu.addAction(download_image_action)
           menu.addSeparator()
        if not result.linkUrl().isEmpty():
           open_new_win_action = self.pageAction(QWebEnginePage.OpenLinkInNewWindow)
           open_new_win_action.setText('Open in New Tab')
           open_new_win_action.setIcon(QIcon(':/list-add.png'))
           menu.addAction(open_new_win_action)
           copy_link_action = self.pageAction(QWebEnginePage.CopyLinkToClipboard)
           copy_link_action.setIcon(QIcon(':/quartz.png'))
           menu.addAction(copy_link_action)
           download_link_action = self.pageAction(QWebEnginePage.DownloadLinkToDisk)
           download_link_action.setText('Download Link')
           download_link_action.setIcon(QIcon(':/document-save.png'))
           menu.addAction(download_link_action)
        if src != '':
           self.src_url = src
           menu.addAction(QIcon(':/document-save.png'), 'Download Content', self.downloadContent)
        auto_refresh_action = QAction(QIcon(':/view-refresh.png'), "Auto Refresh", self)
        auto_refresh_action.setCheckable(True)
        auto_refresh_action.setChecked(self.timer.isActive())
        auto_refresh_action.triggered.connect(self.toggleAutoRefresh)
        menu.addAction(auto_refresh_action)
        if result.imageUrl().isEmpty() and result.linkUrl().isEmpty():
           edit_page_action = QAction(QIcon(':/edit.png'), "Edit Page", self)
           edit_page_action.setCheckable(True)
           edit_page_action.setChecked(self.page().isContentEditable())
           edit_page_action.triggered.connect(self.page().setContentEditable)
           menu.addAction(edit_page_action)
        # Add download videos button
        frames = [self.page().mainFrame()] + self.page().mainFrame().childFrames()
        for frame in frames:
            video = frame.findFirstElement('video')
            if not video.isNull():
                videos_action = QAction(QIcon(':/video-x-generic.png'), "Download Videos", self)
                videos_action.triggered.connect(self.showVideos)
                menu.addAction(videos_action)
                break

        menu.exec_(self.mapToGlobal(event.pos()))

    def saveImageToDisk(self):
        """ This saves an image in page directly without downloading"""
        pm = self.page().mainFrame().hitTestContent(self.rel_pos).pixmap()
        url = self.page().mainFrame().hitTestContent(self.rel_pos).imageUrl()
        filename = filenameFromUrl(url.toString())
        if QFileInfo(filename).suffix() not in ['jpg', 'jpeg', 'png'] :
            filename = os.path.splitext(filename)[0] + '.jpg'
        filepath = QFileDialog.getSaveFileName(self,
                                      "Select Image to Save", downloaddir + filename,
                                      "All Images (*.jpg *.jpeg *.png);;JPEG File (*.jpg);;PNG File (*.png)" )[0]
        if (filepath != '') and pm.save(filepath):
            QMessageBox.information(self, "Successful !","Image has been successfully saved as\n%s"%filepath)

    def downloadContent(self):
        src = QUrl.fromUserInput(self.src_url)
        if src.isRelative():
            src = self.url().resolved(src)
        reqst = QNetworkRequest(src)
        self.page().downloadRequested.emit(reqst)

    def showVideos(self):
        self.videoListRequested.emit()

    def toggleAutoRefresh(self, enable):
        if enable:
            interval, ok = QInputDialog.getInt(self, 'Refresh Interval', 'Enter refresh interval (sec) :', 30, 5, 300)
            if ok:
                self.timer.setInterval(interval*1000)
                self.timer.start()
        else:
            self.timer.stop()

    def resetTimer(self):
        ''' Prevents autorefresh while typing, resets the timer'''
        if self.timer.isActive():
            self.timer.stop()
            self.timer.start()


class UrlEdit(QLineEdit):
    """ Reimplemented QLineEdit to get all selected when double clicked"""
    downloadRequested = pyqtSignal(QNetworkRequest)
    openUrlRequested = pyqtSignal()
    def __init__(self, parent=None):
        super(UrlEdit, self).__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("QLineEdit { padding: 2 2 2 22; background: transparent; border: 1px solid gray; border-radius: 3px;}")
        self.returnPressed.connect(self.onReturnPress)
        # Create button for showing page icon
        self.iconButton = QToolButton(self)
        self.iconButton.setStyleSheet("QToolButton { border: 0; background: transparent; width: 16px; height: 16px; }")
        self.iconButton.move(4,3)
        self.iconButton.setCursor(Qt.PointingHandCursor)
        self.iconButton.clicked.connect(self.selectAll)
        self.setIcon(QIcon(':/quartz.png'))
        #self.setStyleSheet("QLineEdit { background-image:url(:/search.png);background-repeat:no-repeat;\
        #                         padding: 2 2 2 24 ;font-size:15px;}")

    def mouseDoubleClickEvent(self, event):
        self.selectAll()

    def onReturnPress(self):
        if find_mode_on:
            return
        text = self.text()
        if validUrl(text) or text == 'about:home':
            self.openUrlRequested.emit()
            return
        if ( "." not in text) or (" " in text): # If text is not valid url
            url = "https://www.google.com/search?q="+text
            url = url.replace('+', '%2B')
            self.setText(url)
        self.openUrlRequested.emit()

    def contextMenuEvent(self,event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        cliptext = QApplication.clipboard().text()
        if not cliptext == '':
            menu.addAction('Paste and Go', self.pasteNgo)
        menu.addAction("Download Link", self.downloadLink)
        menu.exec_(self.mapToGlobal(event.pos()))

    def pasteNgo(self):
        text = QApplication.clipboard().text()
        self.setText(text)
        self.openUrlRequested.emit()

    def downloadLink(self):
        request = QNetworkRequest(QUrl.fromUserInput(self.text()))
        self.downloadRequested.emit(request)

    def setText(self, string):
        QLineEdit.setText(self, string)
        self.setCursorPosition(0)

    def setIcon(self, icon):
        self.iconButton.setIcon(icon)


def validUrl(url_str):
    """ This checks if the url is valid. Used in GoTo() func"""
    validurl = False
    for each in ("http://", "https://", "ftp://", "ftps://", "file://"):
        if url_str.startswith(each):
            validurl = True
    return validurl

