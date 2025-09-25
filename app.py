import sys
import os
import threading
import csv
from pathlib import Path
from typing import List, Optional
from PySide6.QtCore import Qt, QCoreApplication
from PyQt6 import QtCore, QtGui, QtWidgets
import vlc
from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, USLT, APIC, ID3NoHeaderError
from PIL import Image
from io import BytesIO

SUPPORTED_AUDIO_EXT = {'.mp3', '.flac', '.m4a', '.wav', '.ogg', '.opus'}


def human_size(n: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024.0:
            return f"{n:3.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


def is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_AUDIO_EXT


class VLCPlayer(QtCore.QObject):
    position_changed = QtCore.pyqtSignal(float)
    state_changed = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.timer = QtCore.QTimer()
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._pulse)
        self.current_media_path: Optional[Path] = None

    def _pulse(self):
        if not self.player:
            return
        try:
            pos = self.player.get_position()
            if pos != -1:
                self.position_changed.emit(pos)
        except Exception:
            pass

    def load(self, path: Path):
        media = self.instance.media_new(str(path))
        self.player.set_media(media)
        self.current_media_path = path
        self.state_changed.emit('loaded')

    def play(self):
        self.player.play()
        self.timer.start()
        self.state_changed.emit('playing')

    def pause(self):
        self.player.pause()
        self.state_changed.emit('paused')

    def stop(self):
        self.player.stop()
        self.timer.stop()
        self.state_changed.emit('stopped')

    def set_position(self, fraction: float):
        try:
            self.player.set_position(fraction)
        except Exception:
            pass

    def set_volume(self, v: int):
        try:
            self.player.audio_set_volume(v)
        except Exception:
            pass


class AudioItem:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.size = path.stat().st_size
        except Exception:
            self.size = 0
        self.tags = {}
        self._load_tags()

    def _load_tags(self):
        try:
            f = MutagenFile(self.path)
            self.tags = {}
            if f is None:
                return
            if f.tags is not None:
                # quick generic
                for k, v in f.tags.items():
                    try:
                        self.tags[k] = str(v)
                    except Exception:
                        self.tags[k] = repr(v)
            if self.path.suffix.lower() == '.mp3':
                try:
                    id3 = ID3(self.path)
                    self.tags['title'] = id3.get('TIT2').text[0] if id3.get('TIT2') else ''
                    self.tags['artist'] = id3.get('TPE1').text[0] if id3.get('TPE1') else ''
                    self.tags['album'] = id3.get('TALB').text[0] if id3.get('TALB') else ''
                    self.tags['year'] = str(id3.get('TDRC')) if id3.get('TDRC') else ''
                    self.tags['track'] = id3.get('TRCK').text[0] if id3.get('TRCK') else ''
                    self.tags['genre'] = id3.get('TCON').text[0] if id3.get('TCON') else ''
                    self.tags['comment'] = id3.get('COMM::eng').text[0] if id3.get('COMM::eng') else ''
                    self.tags['lyrics'] = id3.get('USLT::eng').text if id3.get('USLT::eng') else ''
                except Exception:
                    pass
            else:
                easy = MutagenFile(self.path, easy=True)
                if easy:
                    self.tags['title'] = easy.get('title', [''])[0]
                    self.tags['artist'] = easy.get('artist', [''])[0]
                    self.tags['album'] = easy.get('album', [''])[0]
                    self.tags['year'] = easy.get('date', [''])[0]
                    self.tags['genre'] = easy.get('genre', [''])[0]
                    self.tags['lyrics'] = easy.get('lyrics', [''])[0]
        except Exception as e:
            print("read tags error:", e)

    def save_tags(self, fields: dict, write_lyrics: Optional[str] = None, cover_bytes: Optional[bytes] = None):
        try:
            if self.path.suffix.lower() == '.mp3':
                try:
                    id3 = ID3(self.path)
                except ID3NoHeaderError:
                    id3 = ID3()
                if 'title' in fields:
                    id3.delall('TIT2'); id3.add(mutagen_id3_frame('TIT2', fields.get('title', '')))
                if 'artist' in fields:
                    id3.delall('TPE1'); id3.add(mutagen_id3_frame('TPE1', fields.get('artist', '')))
                if 'album' in fields:
                    id3.delall('TALB'); id3.add(mutagen_id3_frame('TALB', fields.get('album', '')))
                if 'year' in fields:
                    id3.delall('TDRC'); id3.add(mutagen_id3_frame('TDRC', fields.get('year', '')))
                if 'track' in fields:
                    id3.delall('TRCK'); id3.add(mutagen_id3_frame('TRCK', fields.get('track', '')))
                if 'genre' in fields:
                    id3.delall('TCON'); id3.add(mutagen_id3_frame('TCON', fields.get('genre', '')))
                if 'comment' in fields:
                    id3.delall('COMM'); from mutagen.id3 import COMM as MUTCOMM; id3.add(MUTCOMM(encoding=3, lang='eng', desc='', text=fields.get('comment','')))
                if write_lyrics is not None:
                    id3.delall('USLT'); id3.add(USLT(encoding=3, lang='eng', desc='', text=write_lyrics))
                if cover_bytes is not None:
                    id3.delall('APIC'); id3.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='cover', data=cover_bytes))
                id3.save(self.path, v2_version=3)
            else:
                f = MutagenFile(self.path, easy=True)
                if f is not None:
                    for k, v in fields.items():
                        if v is None:
                            continue
                        f[k] = v
                    if write_lyrics is not None:
                        try:
                            f['lyrics'] = write_lyrics
                        except Exception:
                            pass
                    f.save()
        except Exception as e:
            print("save tags error:", e)


def mutagen_id3_frame(frameid: str, text: str):
    from mutagen.id3 import Frames, ID3, TextFrame
    # create text frame generically
    from mutagen.id3 import Frames as F
    from mutagen.id3 import Encoding
    from mutagen.id3 import ID3 as ID3cls
    # fallback simple: use frame class by name if available
    try:
        from mutagen.id3 import Frames, TIT2, TPE1, TALB, TDRC, TRCK, TCON
        mapping = {'TIT2': TIT2, 'TPE1': TPE1, 'TALB': TALB, 'TDRC': TDRC, 'TRCK': TRCK, 'TCON': TCON}
        if frameid in mapping:
            return mapping[frameid](encoding=3, text=text)
    except Exception:
        pass
    # generic text frame
    from mutagen.id3 import TXXX
    return TXXX(encoding=3, desc=frameid, text=text)


class AudioTableModel(QtCore.QAbstractTableModel):
    HEADERS = ['#', 'Title', 'Artist', 'Album', 'Year', 'Track', 'Genre', 'File', 'Size']

    def __init__(self, items: List[AudioItem] = None):
        super().__init__()
        self.items = items or []

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self.items)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(self.HEADERS)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        col = index.column()
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return index.row() + 1
            if col == 1:
                return item.tags.get('title') or item.path.stem
            if col == 2:
                return item.tags.get('artist')
            if col == 3:
                return item.tags.get('album')
            if col == 4:
                return item.tags.get('year')
            if col == 5:
                return item.tags.get('track')
            if col == 6:
                return item.tags.get('genre')
            if col == 7:
                return str(item.path.name)
            if col == 8:
                return human_size(item.size)
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return str(item.path)
        return None

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if orientation == QtCore.Qt.Orientation.Horizontal and role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def add_items(self, new_items: List[AudioItem]):
        self.beginResetModel()
        self.items.extend(new_items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self.items = []
        self.endResetModel()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Meta Note')
        self.resize(1200, 760)
        # self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint)
        # self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.central = QtWidgets.QWidget()
        self.setCentralWidget(self.central)
        self.player = VLCPlayer()
        self.player.position_changed.connect(self.on_position_changed)
        self.player.state_changed.connect(self.on_player_state_changed)
        self._build_ui()
        self.items: List[AudioItem] = []
        self.current_item: Optional[AudioItem] = None
        self._apply_styles()


    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self.central)
        top_layout = QtWidgets.QHBoxLayout()

        left_v = QtWidgets.QVBoxLayout()
        toolbar = QtWidgets.QHBoxLayout()
        btn_import = QtWidgets.QPushButton('Import folder')
        btn_import.clicked.connect(self.import_folder)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('Search title / artist / album ...')
        self.search.textChanged.connect(self.apply_filter)
        toolbar.addWidget(btn_import)
        toolbar.addWidget(self.search)
        left_v.addLayout(toolbar)

        self.table_model = AudioTableModel([])
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.table_double_clicked)
        left_v.addWidget(self.table)

        batch_bar = QtWidgets.QHBoxLayout()
        self.btn_batch_apply = QtWidgets.QPushButton('Apply inspector → selected')
        self.btn_batch_apply.clicked.connect(self.batch_apply_to_selected)
        self.btn_apply_all = QtWidgets.QPushButton('Apply inspector → all')
        self.btn_apply_all.clicked.connect(self.batch_apply_to_all)
        self.btn_bulk_rename = QtWidgets.QPushButton('Bulk rename selected')
        self.btn_bulk_rename.clicked.connect(self.bulk_rename_selected)
        self.btn_export = QtWidgets.QPushButton('Export CSV')
        self.btn_export.clicked.connect(self.export_csv)
        batch_bar.addWidget(self.btn_batch_apply)
        batch_bar.addWidget(self.btn_apply_all)
        batch_bar.addWidget(self.btn_bulk_rename)
        batch_bar.addWidget(self.btn_export)
        left_v.addLayout(batch_bar)

        top_layout.addLayout(left_v, 3)

        right_v = QtWidgets.QVBoxLayout()
        self.cover_label = QtWidgets.QLabel()
        self.cover_label.setFixedSize(240, 240)
        self.cover_label.setStyleSheet('border-radius:12px; background: rgba(255,255,255,10);')
        right_v.addWidget(self.cover_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        form = QtWidgets.QFormLayout()
        self.input_title = QtWidgets.QLineEdit()
        self.input_artist = QtWidgets.QLineEdit()
        self.input_album = QtWidgets.QLineEdit()
        self.input_year = QtWidgets.QLineEdit()
        self.input_track = QtWidgets.QLineEdit()
        self.input_genre = QtWidgets.QLineEdit()
        self.input_comment = QtWidgets.QLineEdit()
        form.addRow('Title', self.input_title)
        form.addRow('Artist', self.input_artist)
        form.addRow('Album', self.input_album)
        form.addRow('Year', self.input_year)
        form.addRow('Track', self.input_track)
        form.addRow('Genre', self.input_genre)
        form.addRow('Comment', self.input_comment)
        right_v.addLayout(form)

        right_v.addWidget(QtWidgets.QLabel('Lyrics / Notes'))
        self.lyrics_edit = QtWidgets.QTextEdit()
        self.lyrics_edit.setFixedHeight(160)
        right_v.addWidget(self.lyrics_edit)

        rbtns = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton('Save metadata')
        self.btn_save.clicked.connect(self.save_metadata_current)
        self.btn_replace_cover = QtWidgets.QPushButton('Replace cover')
        self.btn_replace_cover.clicked.connect(self.replace_cover)
        rbtns.addWidget(self.btn_save)
        rbtns.addWidget(self.btn_replace_cover)
        right_v.addLayout(rbtns)

        player_box = QtWidgets.QGroupBox('Player')
        p_layout = QtWidgets.QVBoxLayout()
        ph = QtWidgets.QHBoxLayout()
        self.btn_prev = QtWidgets.QPushButton('⏮')
        self.btn_play = QtWidgets.QPushButton('▶')
        self.btn_pause = QtWidgets.QPushButton('⏸')
        self.btn_stop = QtWidgets.QPushButton('⏹')
        self.btn_next = QtWidgets.QPushButton('⏭')
        self.btn_play.clicked.connect(self.play_selected)
        self.btn_pause.clicked.connect(self.player.pause)
        self.btn_stop.clicked.connect(self.player.stop)
        self.btn_prev.clicked.connect(self.play_prev)
        self.btn_next.clicked.connect(self.play_next)
        ph.addWidget(self.btn_prev); ph.addWidget(self.btn_play); ph.addWidget(self.btn_pause); ph.addWidget(self.btn_stop); ph.addWidget(self.btn_next)
        p_layout.addLayout(ph)
        self.seek = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.sliderMoved.connect(self.on_seek)
        p_layout.addWidget(self.seek)
        vol_layout = QtWidgets.QHBoxLayout()
        self.vol = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(80)
        self.vol.valueChanged.connect(self.player.set_volume)
        vol_layout.addWidget(QtWidgets.QLabel('Vol'))
        vol_layout.addWidget(self.vol)
        p_layout.addLayout(vol_layout)
        player_box.setLayout(p_layout)
        right_v.addWidget(player_box)

        top_layout.addLayout(right_v, 2)

        main_layout.addLayout(top_layout)

        footer = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel('Ready')
        footer.addWidget(self.status_label)
        main_layout.addLayout(footer)

    def _apply_styles(self):
        style = """
        QMainWindow { background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(6,6,20,240), stop:1 rgba(18,6,40,240)); color: #dfefff; }
        QWidget { color: #e6f0ff; font-family: Inter, Roboto, Arial; }
        QTableView { background: rgba(255,255,255,6); gridline-color: rgba(255,255,255,8); }
        QHeaderView::section { background: rgba(255,255,255,4); padding:6px; }
        QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #5b2bff, stop:1 #00c2ff);
                      border-radius:8px; padding:8px; color: white; font-weight:600; }
        QPushButton:disabled { background: rgba(255,255,255,20); color: rgba(255,255,255,100); }
        QLineEdit, QTextEdit { background: rgba(255,255,255,6); border-radius:8px; padding:6px; }
        QLabel { color: #cfe8ff; }
        QGroupBox { border: 1px solid rgba(255,255,255,6); border-radius:10px; padding:8px; }
        """
        self.setStyleSheet(style)
        effect = QtWidgets.QGraphicsDropShadowEffect(blurRadius=30, xOffset=0, yOffset=12)
        self.central.setGraphicsEffect(effect)

    def import_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select music folder')
        if not folder:
            return
        self.status_label.setText('Scanning folder...')
        threading.Thread(target=self._scan_folder, args=(Path(folder),), daemon=True).start()

    def _scan_folder(self, folder: Path):
        found = []
        for p in folder.rglob('*'):
            if is_audio_file(p):
                found.append(AudioItem(p))
        QtCore.QMetaObject.invokeMethod(self, '_finish_scan', QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(object, found))

    @QtCore.pyqtSlot(object)
    def _finish_scan(self, found):
        self.items = found
        self.table_model.clear()
        self.table_model.add_items(self.items)
        self.status_label.setText(f'Scanned {len(found)} audio files')

    def apply_filter(self, text=''):
        t = text.strip().lower()
        if not t:
            self.table_model.beginResetModel(); self.table_model.items = self.items; self.table_model.endResetModel(); return
        filtered = [it for it in self.items if t in (it.tags.get('title','') or '').lower() or t in (it.tags.get('artist','') or '').lower() or t in (it.tags.get('album','') or '').lower()]
        self.table_model.beginResetModel(); self.table_model.items = filtered; self.table_model.endResetModel()

    def table_double_clicked(self, idx):
        row = idx.row()
        item = self.table_model.items[row]
        self.load_into_inspector(item)
        self.player.load(item.path)
        self.player.play()

    def load_into_inspector(self, item: AudioItem):
        self.current_item = item
        self.input_title.setText(item.tags.get('title','') or '')
        self.input_artist.setText(item.tags.get('artist','') or '')
        self.input_album.setText(item.tags.get('album','') or '')
        self.input_year.setText(item.tags.get('year','') or '')
        self.input_track.setText(item.tags.get('track','') or '')
        self.input_genre.setText(item.tags.get('genre','') or '')
        self.input_comment.setText(item.tags.get('comment','') or '')
        self.lyrics_edit.setPlainText(item.tags.get('lyrics','') or '')
        cover = self._get_cover_bytes(item.path)
        if cover:
            pix = QtGui.QPixmap(); pix.loadFromData(cover)
            self.cover_label.setPixmap(pix.scaled(self.cover_label.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation))
        else:
            self.cover_label.setPixmap(QtGui.QPixmap())

    def _get_cover_bytes(self, path: Path) -> Optional[bytes]:
        try:
            if path.suffix.lower() == '.mp3':
                id3 = ID3(path)
                apic = next((v for k, v in id3.items() if k.startswith('APIC')), None)
                if apic:
                    return apic.data
            else:
                f = MutagenFile(path)
                if hasattr(f, 'pictures') and f.pictures:
                    return f.pictures[0].data
        except Exception:
            pass
        return None

    def save_metadata_current(self):
        if not self.current_item:
            QtWidgets.QMessageBox.warning(self, 'No file', 'No file loaded in inspector')
            return
        fields = {
            'title': self.input_title.text(),
            'artist': self.input_artist.text(),
            'album': self.input_album.text(),
            'year': self.input_year.text(),
            'track': self.input_track.text(),
            'genre': self.input_genre.text(),
            'comment': self.input_comment.text(),
        }
        lyrics = self.lyrics_edit.toPlainText()
        self.current_item.save_tags(fields, write_lyrics=lyrics)
        self.current_item._load_tags()
        self.status_label.setText(f'Saved metadata: {self.current_item.path.name}')
        self.table_model.beginResetModel(); self.table_model.endResetModel()

    def batch_apply_to_selected(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QtWidgets.QMessageBox.information(self, 'Select rows', 'Select rows to apply changes')
            return
        items = [self.table_model.items[i.row()] for i in sel]
        self._apply_fields_to_items(items)

    def batch_apply_to_all(self):
        if not self.items:
            return
        self._apply_fields_to_items(self.items)

    def _apply_fields_to_items(self, items: List[AudioItem]):
        fields = {}
        for k, w in [('title', self.input_title), ('artist', self.input_artist), ('album', self.input_album),
                     ('year', self.input_year), ('track', self.input_track), ('genre', self.input_genre),
                     ('comment', self.input_comment)]:
            v = w.text().strip()
            if v:
                fields[k] = v
        lyrics = self.lyrics_edit.toPlainText()
        for it in items:
            it.save_tags(fields, write_lyrics=lyrics if lyrics else None)
            it._load_tags()
        self.table_model.beginResetModel(); self.table_model.endResetModel()
        QtWidgets.QMessageBox.information(self, 'Done', f'Applied to {len(items)} files')

    def bulk_rename_selected(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QtWidgets.QMessageBox.information(self, 'Select rows', 'Select rows to rename')
            return
        items = [self.table_model.items[i.row()] for i in sel]
        for it in items:
            try:
                ext = it.path.suffix
                artist = it.tags.get('artist') or ''
                title = it.tags.get('title') or it.path.stem
                safe_artist = sanitize_filename(artist) or 'Unknown'
                safe_title = sanitize_filename(title) or it.path.stem
                new_name = f"{safe_artist} - {safe_title}{ext}"
                new_path = it.path.with_name(new_name)
                it.path.rename(new_path)
                it.path = new_path
                it._load_tags()
            except Exception as e:
                print("rename error:", e)
        self.table_model.beginResetModel(); self.table_model.endResetModel()
        QtWidgets.QMessageBox.information(self, 'Done', 'Renamed selected files')

    def export_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Export CSV', filter='CSV Files (*.csv)')
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['file', 'title', 'artist', 'album', 'year', 'track', 'genre', 'lyrics'])
            for it in self.table_model.items:
                writer.writerow([str(it.path), it.tags.get('title',''), it.tags.get('artist',''), it.tags.get('album',''), it.tags.get('year',''), it.tags.get('track',''), it.tags.get('genre',''), (it.tags.get('lyrics','') or '').replace('\n','\\n')])
        self.status_label.setText(f'Exported CSV to {path}')

    def replace_cover(self):
        if not self.current_item:
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Select image', filter='Images (*.png *.jpg *.jpeg)')
        if not path:
            return
        with open(path, 'rb') as f:
            b = f.read()
        self.current_item.save_tags({}, write_lyrics=None, cover_bytes=b)
        self.current_item._load_tags()
        self.load_into_inspector(self.current_item)
        self.status_label.setText('Cover replaced')

    def play_selected(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        row = sel[0].row()
        item = self.table_model.items[row]
        self.player.load(item.path)
        self.player.play()
        self.status_label.setText(f'Playing {item.path.name}')

    def play_next(self):
        model_items = self.table_model.items
        if not model_items:
            return
        cur = None
        if self.current_item:
            try:
                cur = model_items.index(self.current_item)
            except ValueError:
                cur = None
        if cur is None:
            idx = 0
        else:
            idx = (cur + 1) % len(model_items)
        self.table.selectRow(idx)
        self.load_into_inspector(model_items[idx])
        self.player.load(model_items[idx].path)
        self.player.play()

    def play_prev(self):
        model_items = self.table_model.items
        if not model_items:
            return
        cur = None
        if self.current_item:
            try:
                cur = model_items.index(self.current_item)
            except ValueError:
                cur = None
        if cur is None:
            idx = 0
        else:
            idx = (cur - 1) % len(model_items)
        self.table.selectRow(idx)
        self.load_into_inspector(model_items[idx])
        self.player.load(model_items[idx].path)
        self.player.play()

    def on_seek(self, val):
        frac = val / 1000.0
        self.player.set_position(frac)

    def on_position_changed(self, frac):
        pos = int(frac * 1000)
        self.seek.blockSignals(True)
        self.seek.setValue(pos)
        self.seek.blockSignals(False)

    def on_player_state_changed(self, state):
        self.status_label.setText('Player: ' + state)

    def table_model_items(self):
        return self.table_model.items

    def on_table_selection_changed(self):
        sel = self.table.selectionModel().selectedRows()
        if sel:
            row = sel[0].row()
            self.load_into_inspector(self.table_model.items[row])

    def table_double_clicked(self, idx):
        row = idx.row()
        self.table.selectRow(row)
        self.load_into_inspector(self.table_model.items[row])
        self.player.load(self.table_model.items[row].path)
        self.player.play()

def sanitize_filename(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum() or ch in " _-").strip().replace(" ", "_")


def main():
    app = QtWidgets.QApplication(sys.argv)
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
