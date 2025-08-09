import sys
import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog, QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit, QTextEdit, QVBoxLayout, QHBoxLayout, QWidget, QSlider
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor, QFont
import vlc
from mutagen import File
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, USLT, ID3NoHeaderError
from PIL import Image
from io import BytesIO

class MusicMetaManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Meta Manager")
        self.setGeometry(100, 100, 1200, 700)
        self.playlist = []
        self.current_index = -1
        self.player = vlc.MediaPlayer()
        self.init_ui()

    def init_ui(self):
        self.setAutoFillBackground(True)
        palette = self.palette()
        gradient = QPalette()
        gradient.setColor(QPalette.ColorRole.Window, QColor(10, 10, 30))
        self.setPalette(gradient)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Year", "Genre", "Path"])
        self.table.cellClicked.connect(self.load_selected_metadata)

        self.btn_import = QPushButton("Import Folder")
        self.btn_import.clicked.connect(self.import_folder)

        self.btn_play = QPushButton("Play")
        self.btn_play.clicked.connect(self.play_track)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.clicked.connect(self.pause_track)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.stop_track)

        self.meta_title = QLineEdit()
        self.meta_artist = QLineEdit()
        self.meta_album = QLineEdit()
        self.meta_year = QLineEdit()
        self.meta_genre = QLineEdit()
        self.lyrics_edit = QTextEdit()

        self.btn_save = QPushButton("Save Metadata")
        self.btn_save.clicked.connect(self.save_metadata)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderMoved.connect(self.set_position)

        layout = QVBoxLayout()
        controls = QHBoxLayout()
        controls.addWidget(self.btn_import)
        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_pause)
        controls.addWidget(self.btn_stop)

        meta_layout = QHBoxLayout()
        meta_layout.addWidget(QLabel("Title"))
        meta_layout.addWidget(self.meta_title)
        meta_layout.addWidget(QLabel("Artist"))
        meta_layout.addWidget(self.meta_artist)
        meta_layout.addWidget(QLabel("Album"))
        meta_layout.addWidget(self.meta_album)
        meta_layout.addWidget(QLabel("Year"))
        meta_layout.addWidget(self.meta_year)
        meta_layout.addWidget(QLabel("Genre"))
        meta_layout.addWidget(self.meta_genre)

        layout.addLayout(controls)
        layout.addWidget(self.table)
        layout.addLayout(meta_layout)
        layout.addWidget(QLabel("Lyrics"))
        layout.addWidget(self.lyrics_edit)
        layout.addWidget(self.btn_save)
        layout.addWidget(self.slider)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if folder:
            self.table.setRowCount(0)
            self.playlist = []
            for root, _, files in os.walk(folder):
                for file in files:
                    if file.lower().endswith((".mp3", ".flac", ".wav", ".m4a")):
                        path = os.path.join(root, file)
                        audio = File(path, easy=True)
                        title = audio.get("title", [""])[0] if audio else ""
                        artist = audio.get("artist", [""])[0] if audio else ""
                        album = audio.get("album", [""])[0] if audio else ""
                        year = audio.get("date", [""])[0] if audio else ""
                        genre = audio.get("genre", [""])[0] if audio else ""
                        row = self.table.rowCount()
                        self.table.insertRow(row)
                        self.table.setItem(row, 0, QTableWidgetItem(title))
                        self.table.setItem(row, 1, QTableWidgetItem(artist))
                        self.table.setItem(row, 2, QTableWidgetItem(album))
                        self.table.setItem(row, 3, QTableWidgetItem(year))
                        self.table.setItem(row, 4, QTableWidgetItem(genre))
                        self.table.setItem(row, 5, QTableWidgetItem(path))
                        self.playlist.append(path)

    def load_selected_metadata(self, row, _):
        path = self.table.item(row, 5).text()
        audio = File(path, easy=True)
        if audio:
            self.meta_title.setText(audio.get("title", [""])[0])
            self.meta_artist.setText(audio.get("artist", [""])[0])
            self.meta_album.setText(audio.get("album", [""])[0])
            self.meta_year.setText(audio.get("date", [""])[0])
            self.meta_genre.setText(audio.get("genre", [""])[0])
        try:
            tags = ID3(path)
            lyrics_tag = tags.getall("USLT")
            if lyrics_tag:
                self.lyrics_edit.setPlainText(lyrics_tag[0].text)
            else:
                self.lyrics_edit.clear()
        except ID3NoHeaderError:
            self.lyrics_edit.clear()
        self.current_index = row

    def play_track(self):
        if self.current_index >= 0 and self.current_index < len(self.playlist):
            self.player.stop()
            self.player = vlc.MediaPlayer(self.playlist[self.current_index])
            self.player.play()

    def pause_track(self):
        self.player.pause()

    def stop_track(self):
        self.player.stop()

    def set_position(self, pos):
        if self.player:
            self.player.set_position(pos / 1000.0)

    def save_metadata(self):
        if self.current_index >= 0:
            path = self.playlist[self.current_index]
            audio = EasyID3(path)
            audio["title"] = self.meta_title.text()
            audio["artist"] = self.meta_artist.text()
            audio["album"] = self.meta_album.text()
            audio["date"] = self.meta_year.text()
            audio["genre"] = self.meta_genre.text()
            audio.save()
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                tags = ID3()
            tags.delall("USLT")
            tags.add(USLT(encoding=3, lang="eng", desc="", text=self.lyrics_edit.toPlainText()))
            tags.save(path)
            self.table.setItem(self.current_index, 0, QTableWidgetItem(self.meta_title.text()))
            self.table.setItem(self.current_index, 1, QTableWidgetItem(self.meta_artist.text()))
            self.table.setItem(self.current_index, 2, QTableWidgetItem(self.meta_album.text()))
            self.table.setItem(self.current_index, 3, QTableWidgetItem(self.meta_year.text()))
            self.table.setItem(self.current_index, 4, QTableWidgetItem(self.meta_genre.text()))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MusicMetaManager()
    window.show()
    sys.exit(app.exec())
