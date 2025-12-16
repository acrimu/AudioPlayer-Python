#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
 Project:   Audio Player (Cross-Platform Python Audio Player)
 File:      AudioPlayer.py
 Author:    Adrian Crimu
 GitHub:    https://github.com/acrimu/AudioPlayer-Python
 License:   MIT License
 Created:   2025-10-30
===============================================================================

 Description:
    A full-featured, cross-platform MP3/audio player built in Python with Tkinter
    and VLC. Designed for macOS, Windows, and Linux, featuring a clean interface
    and playlist persistence.

 Features:
    • Play, Pause, Stop, Next, Previous
    • Progress bar with seek and elapsed time
    • Playlist load/save in JSON format
    • Drag & drop, folder or file add
    • Move songs up/down in the playlist
    • Context menu with right-click / two-finger click
    • Volume control (0-150%)
    • macOS sleep prevention using `caffeinate`
    • Automatic pause when the system goes to sleep

 Requirements:
    Python 3.8+
    Modules:
        - vlc (python-vlc)
        - mutagen
        - tkinter (standard library)
        - objc, Foundation, Cocoa (macOS only)
        - json, os, sys, subprocess (standard)

 Run:
    $ python3 AudioPlayer.py

===============================================================================
"""


import vlc
import os
import json
import time
import queue
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from mutagen import File as MutagenFile

import objc
from Foundation import NSObject
from Cocoa import NSWorkspace
from tkinter import ttk, filedialog
import tkinter as tk
import sys
import subprocess

# Supported audio extensions (used by dialogs and folder scanning)
SUPPORTED_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".wma")

# === Thread-safe queue for macOS sleep notifications ===
sleep_event_queue = queue.Queue()

# === Logic ===
global current_index_playing, index_to_play
current_index_playing = -1
index_to_play = -1

def get_audio_duration(filepath):
    """Try VLC first (works for most formats). Fall back to mutagen if VLC fails."""
    try:
        instance = vlc.Instance()
        media = instance.media_new(filepath)
        # blocking parse to ensure duration available
        media.parse()
        dur_ms = media.get_duration()
        if dur_ms and dur_ms > 0:
            return int(dur_ms / 1000)
    except Exception:
        pass

    # Fallback to mutagen (gives length in seconds if supported)
    try:
        audio = MutagenFile(filepath)
        if audio and hasattr(audio, "info") and getattr(audio.info, "length", None):
            return int(audio.info.length)
    except Exception:
        pass

    return 0

def renumber_tree():
    """Update the 'No.' column to reflect the current order in the tree."""
    for idx, item in enumerate(tree.get_children(), start=1):
        values = list(tree.item(item, "values"))
        values[0] = str(idx)
        tree.item(item, values=values)

# --- play marker helpers ---
def clear_playing_mark():
    """Remove playing marker (▶) and tags from all rows."""
    for item in tree.get_children():
        vals = list(tree.item(item, "values"))
        if vals and len(vals) > 1 and isinstance(vals[1], str) and vals[1].startswith("▶ "):
            vals[1] = vals[1][2:]
            tree.item(item, values=vals)
        # clear tags for safety
        tree.item(item, tags=())

# --- play marker helpers ---
def clear_stop_mark():
    """Remove playing marker (▶) and tags from all rows."""
    for item in tree.get_children():
        vals = list(tree.item(item, "values"))
        if vals and len(vals) > 1 and isinstance(vals[1], str) and vals[1].startswith("■ "):
            vals[1] = vals[1][2:]
            tree.item(item, values=vals)
        # clear tags for safety
        tree.item(item, tags=())

def mark_pause_item(index):
    """Mark the row at `index` as pause (add ⏸ prefix + 'playing' tag) and clear others."""
    children = tree.get_children()
    if not children:
        return
    for i, item in enumerate(children):
        vals = list(tree.item(item, "values"))
        # ensure there's a title column
        if not vals or len(vals) < 2:
            continue
        if i == index:
            # remove stop marker if present
            if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                vals[1] = vals[1][2:]
            if not vals[1].startswith("⏸ "):
                vals[1] = "⏸ " + vals[1]
                tree.item(item, values=vals)
            tree.item(item, tags=("playing",))
        else:
            if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                vals[1] = vals[1][2:]
                tree.item(item, values=vals)
            tree.item(item, tags=())

def mark_playing_item(index):
    """Mark the row at `index` as pause (add ⏸ prefix + 'playing' tag) and clear others."""
    children = tree.get_children()
    if not children:
        return
    for i, item in enumerate(children):
        vals = list(tree.item(item, "values"))
        # ensure there's a title column
        if not vals or len(vals) < 2:
            continue
        if i == index:
            # remove stop marker if present
            if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                vals[1] = vals[1][2:]
            if not vals[1].startswith("▶ "):
                vals[1] = "▶ " + vals[1]
                tree.item(item, values=vals)
            tree.item(item, tags=("playing",))
        else:
            if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                vals[1] = vals[1][2:]
                tree.item(item, values=vals)
            tree.item(item, tags=())

def add_song_to_list(path):
    """Add a file to playlist and populate sensible title/artist for many formats."""
    if not os.path.isfile(path):
        return

    ext = os.path.splitext(path)[1].lower()
    basename = os.path.basename(path)
    title = basename
    artist = "Unknown"

    # MP3: prefer EasyID3
    if ext == ".mp3":
        try:
            tags = EasyID3(path)
            title = tags.get("title", [basename])[0]
            artist = tags.get("artist", ["Unknown"])[0]
        except Exception:
            pass
    else:
        # Other formats: use mutagen generic File and try common tag keys
        try:
            audio = MutagenFile(path)
            if audio and audio.tags:
                # try common keys (many formats provide lists)
                def first_tag(tags, *keys):
                    for k in keys:
                        if k in tags:
                            v = tags[k]
                            try:
                                return v[0] if isinstance(v, (list, tuple)) else str(v)
                            except Exception:
                                return str(v)
                    return None

                t = first_tag(audio.tags, "title", "TITLE", "TIT2", "\xa9nam")
                a = first_tag(audio.tags, "artist", "ARTIST", "TPE1", "\xa9ART")
                if t:
                    title = t
                if a:
                    artist = a
        except Exception:
            pass

    # Append extension label for non-mp3 files (optional UI hint)
    if ext != ".mp3" and ext:
        title = f"{title} [{ext[1:].upper()}]"

    dur = get_audio_duration(path)

    playlist.append(path)
    number_of_songs = len(tree.get_children())
    tree.insert("", "end", values=(str(number_of_songs + 1), title, artist, f"{dur//60:02}:{dur%60:02}"))
    renumber_tree()

def add_folder():
    global last_opened_folder
    folder = filedialog.askdirectory(initialdir=last_opened_folder)
    if not folder:
        return

    #playlist.clear()
    #tree.delete(*tree.get_children())

    # Walk folder recursively and add supported files in a stable order
    for root_dir, dirs, files in os.walk(folder):
        dirs.sort()
        for file in sorted(files):
            if file.lower().endswith(SUPPORTED_EXTS):
                path = os.path.join(root_dir, file)
                add_song_to_list(path)

    # remember last opened folder
    last_opened_folder = folder

    # update numbers and persist playlist
    renumber_tree()
    with open(PLAYLIST_FILE, "w") as f:
        json.dump({"playlist": playlist}, f)

    if player:
        stop_song()

    # Select the first song if available
    if tree.get_children():
        first_item = tree.get_children()[0]
        tree.selection_set(first_item)
        tree.focus(first_item)
        tree.see(first_item)

def add_songs():
    global last_opened_folder
    song_tmp = filedialog.askopenfilenames(
        title="Select Audio Files",
        initialdir=last_opened_folder,
        filetypes=[("Audio Files", "*.mp3 *.wav *.flac *.ogg *.aac *.m4a *.wma"),
                   ("All Files", "*.*")]
    )
    if not song_tmp:
        return
    # Remember the folder of the first selected file
    last_opened_folder = os.path.dirname(song_tmp[0])
    for file in sorted(song_tmp):
        if file.lower().endswith(SUPPORTED_EXTS):
            add_song_to_list(file)
    renumber_tree()
    json.dump({"playlist": playlist}, open(PLAYLIST_FILE, "w"))

def clear_songs_list():
    if player:
        stop_song()
    playlist.clear(); tree.delete(*tree.get_children())
    json.dump({"playlist": playlist}, open(PLAYLIST_FILE, "w"))

def load_saved_playlist():
    if not os.path.exists(PLAYLIST_FILE):
        return
    try:
        data = json.load(open(PLAYLIST_FILE))
        for path in data.get("playlist", []):
            if os.path.exists(path):
                add_song_to_list(path)
    except Exception:
        pass

    json.dump({"playlist": playlist}, open(PLAYLIST_FILE, "w"))

    # 👇 Select the first song if available
    if tree.get_children():
        first_item = tree.get_children()[0]
        tree.selection_set(first_item)
        tree.focus(first_item)
        tree.see(first_item)

def play_selected():
    global current_index, index_to_play, current_index_playing
    sel = tree.selection()
    if sel:
        current_index = tree.index(sel[0])
        
    if paused and current_index_playing == current_index:
        pause_song()
        wait_for_playing_and_update()
        return
    
    if sel:
        index_to_play = current_index
        play_song()
        
def play_song():
    global player, current_song_length, current_index_playing, index_to_play
    try:
        if player and player.get_state() == vlc.State.Playing and current_index_playing == index_to_play:
            return
    except Exception:
        pass
    
    stop_song()
    clear_stop_mark()
    if index_to_play < 0:
        index_to_play = current_index
    current_index_playing = index_to_play
    song = playlist[current_index_playing]
    
    try:
        player = vlc.MediaPlayer(song)
        player.audio_set_volume(int(volume_slider.get()))
        player.play()
    except Exception as e:
        print(f"Error creating/playing media: {e}")
        player = None
        return
    
    try:
        audio = MP3(song)
    except Exception:
        pass

    current_song_length = get_audio_duration(song)
    progress_bar["maximum"] = current_song_length

    label_var.set(f"🎵 Now playing: {os.path.basename(song)}")
    wait_for_playing_and_update()
    check_song_end()
    mark_playing_item(current_index_playing)

def pause_song():
    global paused
    if player:
        try:
            (player.play() if paused else player.pause())
            paused = not paused

            if paused:
                mark_pause_item(current_index_playing)
            else:
                mark_playing_item(current_index_playing)
                wait_for_playing_and_update()
        except Exception as e:
            print(f"Error in pause_song: {e}")

def mark_stopped_item(index):
    """Mark the row at `index` as stopped (■ prefix) but keep the same tag/colors."""
    children = tree.get_children()
    if not children:
        return
    for i, item in enumerate(children):
        vals = list(tree.item(item, "values"))
        if not vals or len(vals) < 2:
            continue
        if i == index:
            # remove playing marker if present
            if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                vals[1] = vals[1][2:]
            # add stopped marker if not present
            if not vals[1].startswith("■ "):
                vals[1] = "■ " + vals[1]
                tree.item(item, values=vals)
            # keep the same visual tag so colors remain
            tree.item(item, tags=("playing",))
        else:
            # remove stopped marker from other rows
            if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                vals[1] = vals[1][2:]
                tree.item(item, values=vals)
            tree.item(item, tags=())

def stop_song():
    global paused
    paused = False
    if player:
        try:
            player.stop()
        except Exception as e:
            print(f"Error stopping player: {e}")
    progress_bar['value'] = 0
    label_var.set("⏹ Stopped")
    time_label.config(text="")
    # keep the same background/foreground for the last played item
    clear_playing_mark()
    if 0 <= current_index_playing < len(playlist):
        mark_stopped_item(current_index_playing)

def skip(step):
    global index_to_play
    index_to_play = (index_to_play + step) % len(playlist)
    play_song()

def update_progress():
    if player is not None and player.get_state() == vlc.State.Playing:
        pos = int(player.get_time() / 1000)
        progress_bar['value'] = pos
        #print("progress_bar value set to ", pos)

        minutes = pos // 60
        seconds = pos % 60
        total = current_song_length
        total_minutes = total // 60
        total_seconds = total % 60

        time_label.config(text=f"{minutes:02}:{seconds:02} / {total_minutes:02}:{total_seconds:02}")

        if pos < total:
            root.after(1000, update_progress)
    elif player and player.get_state() == vlc.State.Ended:
        progress_bar['value'] = 0
        time_label.config(text="")
        if not paused and current_index_playing < len(playlist) - 1:
            skip(1)

def seek_progress(e):
    if player:
        # Click on the progressbar will get e.x that is the x coordinate inside progressbar graphic control
        # This is why we have to calcupate as percentage
        #print("seek_progress click at ", e.x)
        percent = e.x / progress_bar.winfo_width()
        #print("percent is ", percent)
        set_time = int(current_song_length * percent) * 1000
        #print("Set song time to ", set_time)
        player.set_time(set_time)
        update_progress()

def wait_for_playing_and_update():
    if player is not None and player.get_state() == vlc.State.Playing:
        update_progress()
    else:
        root.after(200, wait_for_playing_and_update)  # Retry in 200 ms

def check_song_end():
    global player, current_index_playing
    if player is not None:
        state = player.get_state()
        if state == vlc.State.Ended:
            progress_bar['value'] = 0
            time_label.config(text="")
            if not paused:
                if current_index_playing < len(playlist) - 1:
                    skip(1)
                elif len(playlist) > 0:
                    current_index_playing = 0
                    play_song()
                    # --- Ensure the first song is selected in the tree ---
                    first_item = tree.get_children()[0]
                    #tree.selection_set(first_item)
                    #tree.focus(first_item)
                    tree.see(first_item)
            return
    root.after(1000, check_song_end)

def delete_current_song():
    global player, current_index, current_index_playing

    sel = tree.selection()
    if not sel:
        return
    idx = tree.index(sel[0])
    if idx < 0 or idx >= len(playlist):
        return

    was_playing_deleted = (player is not None and current_index_playing == idx)

    if was_playing_deleted:
        stop_song()
        player = None

    del playlist[idx]
    tree.delete(sel[0])
    renumber_tree()

    # adjust playing index if it was after deleted index
    if player is not None and current_index_playing > idx:
        current_index_playing -= 1

    if playlist:
        # select next item: same index if it exists, otherwise the new last item
        new_index = idx if idx < len(playlist) else len(playlist) - 1
        current_index = new_index
        if was_playing_deleted:
            current_index_playing = current_index
        item = tree.get_children()[current_index]
        tree.selection_set(item)
        tree.focus(item)
        tree.see(item)
    else:
        current_index = 0
        current_index_playing = 0

    json.dump({"playlist": playlist}, open(PLAYLIST_FILE, "w"))

def save_playlist_as():
    file_path = filedialog.asksaveasfilename(
        defaultextension=".json",
        filetypes=[("JSON Playlist", "*.json"), ("All Files", "*.*")],
        title="Save Playlist As"
    )
    if file_path:
        with open(file_path, "w") as f:
            json.dump({"playlist": playlist}, f)

def load_playlist_from_file():
    file_path = filedialog.askopenfilename(
        defaultextension=".json",
        filetypes=[("JSON Playlist", "*.json"), ("All Files", "*.*")],
        title="Load Playlist"
    )
    if file_path:
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                playlist.clear()
                tree.delete(*tree.get_children())
                for path in data.get("playlist", []):
                    add_song_to_list(path)
        except Exception as e:
            ttk.messagebox.showerror("Error", f"Failed to load playlist:\n{e}")

        # Select the first song if available
        if tree.get_children():
            first_item = tree.get_children()[0]
            tree.selection_set(first_item)
            tree.focus(first_item)
            tree.see(first_item)

def move_song(old_index, new_index):
    """Move song in playlist and reorder the Treeview. Keep selection/play indexes in sync."""
    global current_index, current_index_playing
    print(f"move_song from {old_index} to {new_index}")
    if old_index == new_index:
        return
    if not (0 <= old_index < len(playlist)) or not (0 <= new_index < len(playlist)):
        return

    # move in playlist
    item = playlist.pop(old_index)
    playlist.insert(new_index, item)

    # capture current tree values and reorder
    values = [list(tree.item(c, "values")) for c in tree.get_children()]
    moved_vals = values.pop(old_index)
    values.insert(new_index, moved_vals)

    # rebuild tree from reordered values
    tree.delete(*tree.get_children())
    for i, vals in enumerate(values, start=1):
        vals[0] = str(i)
        tree.insert("", "end", values=vals)

    # adjust selection index
    if current_index == old_index:
        current_index = new_index
    elif old_index < current_index <= new_index:
        current_index -= 1
    elif new_index <= current_index < old_index:
        current_index += 1

    # adjust playing index similarly
    if current_index_playing == old_index:
        current_index_playing = new_index
    elif old_index < current_index_playing <= new_index:
        current_index_playing -= 1
    elif new_index <= current_index_playing < old_index:
        current_index_playing += 1

    renumber_tree()

    # restore selection and focus
    if tree.get_children():
        #sel_index = max(0, min(current_index, len(tree.get_children()) - 1))
        item_id = tree.get_children()[new_index]
        tree.selection_set(item_id)
        tree.focus(item_id)
        tree.see(item_id)

    # update visual markers
    if player is not None:
        # there's an active player; mark playing item
        if 0 <= current_index_playing < len(playlist):
            mark_playing_item(current_index_playing)
        else:
            clear_playing_mark()
    else:
        # no active player: keep stopped marker if applicable
        clear_stop_mark()
        if 0 <= current_index_playing < len(playlist):
            mark_stopped_item(current_index_playing)

    # persist playlist
    with open(PLAYLIST_FILE, "w") as f:
        json.dump({"playlist": playlist}, f)


def move_selected_up():
    print("move_selected_up called")
    sel = tree.selection()
    if not sel:
        return
    idx = tree.index(sel[0])
    if idx <= 0:
        return
    move_song(idx, idx - 1)


def move_selected_down():
    print("move_selected_down called")
    sel = tree.selection()
    if not sel:
        return
    idx = tree.index(sel[0])
    if idx >= len(playlist) - 1:
        return
    move_song(idx, idx + 1)

# === Context Menu ===
def show_context_menu(event):
    # Select the row under mouse
    row_id = tree.identify_row(event.y)
    if row_id:
        tree.selection_set(row_id)
        context_menu.tk_popup(event.x_root, event.y_root)



PLAYLIST_FILE = "last_playlist.json"
playlist, current_index, paused, player, current_song_length = [], 0, False, None, 0
last_opened_folder = os.path.expanduser("~")  # Default to home folder

# === Setup GUI ===
root = tk.Tk()
#style = ttk.Style(root)
#style.theme_use("clam")  # Better button look
root.title("🎵 Audio Player")
root.geometry("750x580")
root.minsize(750, 500)
#root.configure(bg="#2c2c2c")

# === Fonts and Colors ===
#font_main = ("Segoe UI", 11)
#bg_main = "#2c2c2c"
#fg_main = "#808080"
#btn_color = "#3a3a3a"

# === Treeview ===
tree_frame = ttk.Frame(root)
tree_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(10, 5))

columns = ("No.", "Title", "Artist", "Duration")
tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
for col in columns:
    tree.heading(col, text=col)
tree.column("No.", width=40)
tree.column("Title", width=300)
tree.column("Artist", width=180)
tree.column("Duration", width=100, anchor='center')

# configure a tag style for the playing item (change foreground to desired color)
# foreground = text color, background = row background
tree.tag_configure("playing", background="#6A6153", foreground="#8dff96")

scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
tree.configure(yscrollcommand=scroll.set)
tree.bind("<Double-1>", lambda e: play_selected())
tree.grid(row=0, column=0, sticky="nsew")
scroll.grid(row=0, column=1, sticky='ns')
tree_frame.grid_rowconfigure(0, weight=1)
tree_frame.grid_columnconfigure(0, weight=1)

# === Now Playing Label ===
label_var = tk.StringVar()
ttk.Label(root, textvariable=label_var).pack(pady=(5, 5))

# === Progress + Time ===
progress_bar = ttk.Progressbar(root, orient="horizontal", length=600, mode="determinate")
progress_bar.pack(pady=4)
progress_bar.bind("<Button-1>", lambda e: seek_progress(e))

time_label = ttk.Label(root, text="")
time_label.pack()

# === Buttons ===
btn_frame = ttk.Frame(root)
btn_frame.pack(pady=12)

def add_btn(txt, cmd, col): 
    ttk.Button(btn_frame, text=txt, command=cmd, width=5)\
        .grid(row=0, column=col, padx=6)

add_btn("Prev", lambda: skip(-1), 0)
add_btn("Play", play_selected, 1)
add_btn("Pause", pause_song, 2)
add_btn("Stop", stop_song, 3)
add_btn("Next", lambda: skip(1), 4)

# === Volume Slider with 0–150% and % Display ===
vol_frame = ttk.Frame(root)
vol_frame.pack(pady=5)

ttk.Label(vol_frame, text="Volume").pack(side=tk.LEFT)

volume_percent = tk.StringVar(value="100%")  # Default: 100%

def on_volume_change(val):
    percent = int(float(val))
    volume_percent.set(f"{percent}%")
    if player:
        player.audio_set_volume(min(percent, 150))  # VLC max = 150

volume_slider = tk.Scale(vol_frame, from_=0, to=150, orient=tk.HORIZONTAL, resolution=1,
                         command=on_volume_change,
                         troughcolor="#555", highlightthickness=0, sliderlength=15, width=10,
                         showvalue=0, length=150)
volume_slider.set(100)  # Default value
volume_slider.pack(side=tk.LEFT, padx=8)

ttk.Label(vol_frame, textvariable=volume_percent).pack(side=tk.LEFT, padx=6)

# === Buttons ===
btn2_frame = ttk.Frame(root)
btn2_frame.pack(pady=12)

# make all six control buttons the same visual width
BTN2_WIDTH = 12

# === Load Folder Button ===
ttk.Button(btn2_frame, text="Add folder", command=lambda: add_folder(), width=BTN2_WIDTH
           ).grid(row=0, column=0, padx=2)

# === Add Songs Button ===
ttk.Button(btn2_frame, text="Add songs", command=lambda: add_songs(), width=BTN2_WIDTH
           ).grid(row=0, column=1, padx=2)

# === Clear Button ===
ttk.Button(btn2_frame, text="Delete", command=lambda: delete_current_song(), width=BTN2_WIDTH
           ).grid(row=0, column=2, padx=2)

# === Clear Button ===
ttk.Button(btn2_frame, text="Clear", command=lambda: clear_songs_list(), width=BTN2_WIDTH
           ).grid(row=0, column=3, padx=2)

# === Save Playlist Button ===
ttk.Button(btn2_frame, text="Save playlist as...", command=save_playlist_as, width=BTN2_WIDTH
           ).grid(row=1, column=0, padx=2)

# === Load Playlist Button ===
ttk.Button(btn2_frame, text="Load playlist...", command=load_playlist_from_file, width=BTN2_WIDTH
           ).grid(row=1, column=1, padx=2)

# === Move Up / Move Down Buttons ===
ttk.Button(btn2_frame, text="Move up", command=lambda: move_selected_up(), width=BTN2_WIDTH
           ).grid(row=1, column=2, padx=2)
ttk.Button(btn2_frame, text="Move down", command=lambda: move_selected_down(), width=BTN2_WIDTH
           ).grid(row=1, column=3, padx=2)


context_menu = tk.Menu(root, tearoff=0)
context_menu.add_command(label="Delete from list", command=lambda: delete_current_song())
context_menu.add_command(label="Move up", command=lambda: move_selected_up())
context_menu.add_command(label="Move down", command=lambda: move_selected_down())

tree.bind("<Button-2>", show_context_menu)  # Two finger click on Mac
tree.bind("<Button-3>", show_context_menu)  # Right-click on Windows/Linux
tree.bind("<Control-Button-1>", show_context_menu)  # Ctrl+Click on Mac

# keyboard shortcuts for quick reordering
root.bind_all("<Control-Up>", lambda e: move_selected_up())
root.bind_all("<Control-Down>", lambda e: move_selected_down())

# === Sleep Listener ===
class SleepListener(NSObject):
    def init(self):
        objc.super(SleepListener, self).init()
        return self

    def start(self):
        try:
            NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
                self, objc.selector(self.handleSleep_, signature=b'v@:@'),
                "NSWorkspaceWillSleepNotification", None)
        except Exception as e:
            print(f"Error starting sleep listener: {e}")

    def stop(self):
        try:
            NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_name_object_(
                self, "NSWorkspaceWillSleepNotification", None)
        except Exception as e:
            print(f"Error stopping sleep listener: {e}")

    def handleSleep_(self, notification):
        # Put event in thread-safe queue instead of calling Tkinter directly
        # This avoids GIL issues with PyObjC running on a different thread
        try:
            sleep_event_queue.put("sleep", block=False)
        except Exception as e:
            print(f"Error queuing sleep event: {e}")

# create instance
sleep_listener = SleepListener.alloc().init()

# --- Sleep listener checkbox ---
sleep_listener_enabled = tk.BooleanVar(value=True)  # default checked

def toggle_sleep_listener():
    if sleep_listener_enabled.get():
        try:
            sleep_listener.start()
        except Exception:
            pass
    else:
        try:
            sleep_listener.stop()
        except Exception:
            pass

ttk.Checkbutton(btn2_frame, text="Pause on sleep", variable=sleep_listener_enabled,
                command=toggle_sleep_listener()).grid(row=1, column=4, padx=6)

# start listener if default enabled
if sleep_listener_enabled.get():
    try:
        sleep_listener.start()
    except Exception:
        pass

def process_sleep_events():
    """Check the sleep event queue and handle pause if needed."""
    try:
        while True:
            event = sleep_event_queue.get_nowait()
            if event == "sleep":
                # Safe pause without directly touching Tkinter from another thread
                global paused, player
                if player:
                    try:
                        # Completely stop and pause the player
                        player.pause()
                        paused = True  # Mark as paused so it doesn't auto-resume on wake
                        mark_pause_item(current_index_playing)
                    except Exception as e:
                        print(f"Error pausing on sleep: {e}")
    except queue.Empty:
        pass
    except Exception as e:
        print(f"Error processing sleep events: {e}")
    finally:
        # Schedule the next check
        root.after(100, process_sleep_events)

# === Start ===
load_saved_playlist()

# Start checking for sleep events
process_sleep_events()

root.mainloop()
