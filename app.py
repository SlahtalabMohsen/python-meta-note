import os
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.aac import AAC
from mutagen.wave import WAVE
from mutagen.id3 import ID3, USLT
from tkinter import Tk, Label, Button, Entry, filedialog, messagebox, Menu, StringVar, Text, Listbox
import pygame

# Initialize pygame mixer for audio playback
pygame.mixer.init()

# Function to change metadata for supported formats
def change_metadata(file_path, artist=None, album=None, title=None, year=None, lyrics=None):
    """
    Change metadata (artist, album, title, year, lyrics) for supported audio formats.
    Supported formats: MP3, FLAC, AAC, WAV.
    """
    try:
        if file_path.endswith(".mp3"):
            audio = EasyID3(file_path)
            if lyrics:
                id3 = ID3(file_path)
                id3.add(USLT(encoding=3, lang='eng', desc='', text=lyrics))
                id3.save()
        elif file_path.endswith(".flac"):
            audio = FLAC(file_path)
            if lyrics:
                audio["lyrics"] = lyrics
        elif file_path.endswith(".aac"):
            audio = AAC(file_path)
            if lyrics:
                audio["lyrics"] = lyrics
        elif file_path.endswith(".wav"):
            audio = WAVE(file_path)
            if lyrics:
                audio["lyrics"] = lyrics
        else:
            return False

        if artist:
            audio['artist'] = artist
        if album:
            audio['album'] = album
        if title:
            audio['title'] = title
        if year:
            audio['date'] = year if file_path.endswith(".mp3") else str(year)
        audio.save()
        return True
    except Exception as e:
        print(f"Error changing metadata: {e}")
        return False

# Function to rename files
def rename_file(file_path, new_name):
    """
    Rename a file to the specified new name.
    """
    try:
        directory = os.path.dirname(file_path)
        new_path = os.path.join(directory, new_name)
        os.rename(file_path, new_path)
        return True
    except Exception as e:
        print(f"Error renaming file: {e}")
        return False

# Function to bulk change metadata
def bulk_change_metadata():
    """
    Change metadata for all files in the selected folder.
    """
    folder_path = folder_path_var.get()
    artist = artist_var.get()
    album = album_var.get()
    title = title_var.get()
    year = year_var.get()
    lyrics = lyrics_text.get("1.0", "end-1c")

    if not folder_path:
        messagebox.showwarning("Error", "Please select a folder.")
        return

    for filename in os.listdir(folder_path):
        if filename.endswith((".mp3", ".flac", ".aac", ".wav")):
            file_path = os.path.join(folder_path, filename)
            if change_metadata(file_path, artist, album, title, year, lyrics):
                print(f"Metadata for {filename} updated successfully.")
            else:
                print(f"Error updating metadata for {filename}.")

    messagebox.showinfo("Complete", "Metadata updated successfully.")

# Function to bulk rename files
def bulk_rename_files():
    """
    Rename all files in the selected folder based on artist and title.
    """
    folder_path = folder_path_var.get()
    artist = artist_var.get()
    title = title_var.get()

    if not folder_path:
        messagebox.showwarning("Error", "Please select a folder.")
        return

    for filename in os.listdir(folder_path):
        if filename.endswith((".mp3", ".flac", ".aac", ".wav")):
            file_path = os.path.join(folder_path, filename)
            if file_path.endswith(".mp3"):
                audio = EasyID3(file_path)
            elif file_path.endswith(".flac"):
                audio = FLAC(file_path)
            elif file_path.endswith(".aac"):
                audio = AAC(file_path)
            elif file_path.endswith(".wav"):
                audio = WAVE(file_path)
            current_title = audio.get('title', ['Unknown Title'])[0]
            new_name = f"{artist} - {current_title}.{filename.split('.')[-1]}" if artist else f"{current_title}.{filename.split('.')[-1]}"
            if rename_file(file_path, new_name):
                print(f"File {filename} renamed to {new_name}.")
            else:
                print(f"Error renaming file {filename}.")

    messagebox.showinfo("Complete", "Files renamed successfully.")

# Function to select a folder
def select_folder():
    """
    Open a dialog to select a folder and load the music files.
    """
    folder_path = filedialog.askdirectory()
    if folder_path:
        folder_path_var.set(folder_path)
        load_music_list(folder_path)

# Function to load music files into the listbox
def load_music_list(folder_path):
    """
    Load all supported audio files from the selected folder into the listbox.
    """
    music_listbox.delete(0, "end")
    for filename in os.listdir(folder_path):
        if filename.endswith((".mp3", ".flac", ".aac", ".wav")):
            music_listbox.insert("end", filename)

# Function to play music
def play_music():
    """
    Play the selected music file and load its lyrics.
    """
    selected_music = music_listbox.get("active")
    if selected_music:
        file_path = os.path.join(folder_path_var.get(), selected_music)
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        load_lyrics(file_path)
        # Enable autoplay
        root.after(100, check_music_status)

# Function to stop music
def stop_music():
    """
    Stop the currently playing music.
    """
    pygame.mixer.music.stop()

# Function to check music status for autoplay
def check_music_status():
    """
    Check if the current song has finished playing and play the next song.
    """
    if not pygame.mixer.music.get_busy():
        next_song()
    root.after(100, check_music_status)

# Function to play the next song
def next_song():
    """
    Play the next song in the list.
    """
    current_index = music_listbox.curselection()
    if current_index:
        next_index = current_index[0] + 1
        if next_index < music_listbox.size():
            music_listbox.selection_clear(0, "end")
            music_listbox.selection_set(next_index)
            music_listbox.activate(next_index)
            play_music()

# Function to load lyrics
def load_lyrics(file_path):
    """
    Load lyrics from the selected music file.
    """
    try:
        if file_path.endswith(".mp3"):
            id3 = ID3(file_path)
            if "USLT::eng" in id3:
                lyrics = id3["USLT::eng"].text
            else:
                lyrics = "Lyrics not found."
        elif file_path.endswith(".flac"):
            audio = FLAC(file_path)
            lyrics = audio.get("lyrics", ["Lyrics not found."])[0]
        elif file_path.endswith(".aac"):
            audio = AAC(file_path)
            lyrics = audio.get("lyrics", ["Lyrics not found."])[0]
        elif file_path.endswith(".wav"):
            audio = WAVE(file_path)
            lyrics = audio.get("lyrics", ["Lyrics not found."])[0]
        else:
            lyrics = "Unsupported file format."
        lyrics_text.delete("1.0", "end")
        lyrics_text.insert("1.0", lyrics)
    except Exception as e:
        print(f"Error loading lyrics: {e}")

# Function to save lyrics
def save_lyrics():
    """
    Save the edited lyrics to the selected music file.
    """
    selected_music = music_listbox.get("active")
    if selected_music:
        file_path = os.path.join(folder_path_var.get(), selected_music)
        lyrics = lyrics_text.get("1.0", "end-1c")
        change_metadata(file_path, lyrics=lyrics)
        messagebox.showinfo("Complete", "Lyrics saved successfully.")

# Create the main window
root = Tk()
root.title("Music Manager")
root.geometry("600x500")

# Variables for the UI
folder_path_var = StringVar()
artist_var = StringVar()
album_var = StringVar()
title_var = StringVar()
year_var = StringVar()

# Menu bar
menu_bar = Menu(root)
root.config(menu=menu_bar)

file_menu = Menu(menu_bar, tearoff=0)
file_menu.add_command(label="Select Folder", command=select_folder)
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit)
menu_bar.add_cascade(label="File", menu=file_menu)

# UI Elements
Label(root, text="Music Folder:").grid(row=0, column=0, padx=10, pady=10)
Entry(root, textvariable=folder_path_var, width=30).grid(row=0, column=1, padx=10, pady=10)
Button(root, text="Select Folder", command=select_folder).grid(row=0, column=2, padx=10, pady=10)

Label(root, text="Artist:").grid(row=1, column=0, padx=10, pady=10)
Entry(root, textvariable=artist_var, width=30).grid(row=1, column=1, padx=10, pady=10)

Label(root, text="Album:").grid(row=2, column=0, padx=10, pady=10)
Entry(root, textvariable=album_var, width=30).grid(row=2, column=1, padx=10, pady=10)

Label(root, text="Title:").grid(row=3, column=0, padx=10, pady=10)
Entry(root, textvariable=title_var, width=30).grid(row=3, column=1, padx=10, pady=10)

Label(root, text="Year:").grid(row=4, column=0, padx=10, pady=10)
Entry(root, textvariable=year_var, width=30).grid(row=4, column=1, padx=10, pady=10)

Button(root, text="Bulk Change Metadata", command=bulk_change_metadata).grid(row=5, column=1, padx=10, pady=10)
Button(root, text="Bulk Rename Files", command=bulk_rename_files).grid(row=6, column=1, padx=10, pady=10)

# Music listbox
music_listbox = Listbox(root, width=50, height=10)
music_listbox.grid(row=7, column=0, columnspan=3, padx=10, pady=10)

# Play and stop buttons
Button(root, text="Play", command=play_music).grid(row=8, column=0, padx=10, pady=10)
Button(root, text="Stop", command=stop_music).grid(row=8, column=1, padx=10, pady=10)

# Lyrics section
Label(root, text="Lyrics:").grid(row=9, column=0, padx=10, pady=10)
lyrics_text = Text(root, width=50, height=10)
lyrics_text.grid(row=10, column=0, columnspan=2, padx=10, pady=10)
Button(root, text="Save Lyrics", command=save_lyrics).grid(row=10, column=2, padx=10, pady=10)

# Run the application
root.mainloop()