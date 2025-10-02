import tkinter as tk
from tkinter import ttk, filedialog
import os, json, vlc
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3

# === Logic ===

def get_audio_duration(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    try:
        instance = vlc.Instance()
        media = instance.media_new(filepath)
        media.parse()  # blocking
        dur = media.get_duration()
        return int(dur / 1000) if dur > 0 else 0

    except:
        return 0

def renumber_tree():
    """Update the 'No.' column to reflect the current order in the tree."""
    for idx, item in enumerate(tree.get_children(), start=1):
        values = list(tree.item(item, "values"))
        values[0] = str(idx)
        tree.item(item, values=values)

def add_song_to_list(path):
    if not os.path.isfile(path): return
    try:
        tags = EasyID3(path)
        title = tags.get("title", [os.path.basename(path)])[0]
        artist = tags.get("artist", ["Unknown"])[0]
    except:
        title = os.path.basename(path)
        artist = "Unknown"
    ext = os.path.splitext(path)[1].lower()
    if ext != ".mp3":
        title += f" [{ext[1:].upper()}]"
    
    dur = get_audio_duration(path)

    playlist.append(path)
    
    if tree.get_children():
        number_of_songs= tree.get_children().__len__()
    else:
        number_of_songs = 0
        
    tree.insert("", "end", values=(str(number_of_songs+1), title, artist, f"{dur//60:02}:{dur%60:02}"))
    renumber_tree() 

def add_folder():
    global last_opened_folder
    folder = filedialog.askdirectory(initialdir=last_opened_folder, title="Select Folder")
    #folder = filedialog.askdirectory()
    if not folder: return
    last_opened_folder = folder
    # playlist.clear(); tree.delete(*tree.get_children())
    for file in sorted(os.listdir(folder)):
        supported_ext = (".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".wma")
        if file.lower().endswith(supported_ext):
            path = os.path.join(folder, file)
            add_song_to_list(path)
    renumber_tree() 
    json.dump({"playlist": playlist}, open(PLAYLIST_FILE, "w"))

    if player:
        stop_song()

    # 👇 Select the first song if available
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
    if not song_tmp: return
    # Remember the folder of the first selected file
    last_opened_folder = os.path.dirname(song_tmp[0])
    for file in sorted(song_tmp):
        supported_ext = (".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".wma")
        if file.lower().endswith(supported_ext):
            add_song_to_list(file)
    renumber_tree()
    json.dump({"playlist": playlist}, open(PLAYLIST_FILE, "w"))

def clear_songs_list():
    if player:
        stop_song()
    playlist.clear(); tree.delete(*tree.get_children())
    json.dump({"playlist": playlist}, open(PLAYLIST_FILE, "w"))

def load_saved_playlist():
    if not os.path.exists(PLAYLIST_FILE): return
    try:
        data = json.load(open(PLAYLIST_FILE))
        for path in data.get("playlist", []):
            add_song_to_list(path)
    except: pass

    json.dump({"playlist": playlist}, open(PLAYLIST_FILE, "w"))

    # 👇 Select the first song if available
    if tree.get_children():
        first_item = tree.get_children()[0]
        tree.selection_set(first_item)
        tree.focus(first_item)
        tree.see(first_item)

def play_selected():
    global current_index
    sel = tree.selection()
    if sel:
        current_index = tree.index(sel[0])
        
    if paused and current_index_playing == current_index:
        pause_song()
        wait_for_playing_and_update()
        return
    
    if sel:
        play_song()
        
def play_song():
    global player, current_song_length, current_index_playing
    if player and player.get_state() == vlc.State.Playing and current_index_playing == current_index:
        return
    stop_song()
    current_index_playing = current_index
    song = playlist[current_index]
    player = vlc.MediaPlayer(song)
    player.audio_set_volume(int(volume_slider.get()))
    player.play()
    audio = MP3(song)

    current_song_length = get_audio_duration(song)
    progress_bar["maximum"] = current_song_length
    #print("progress_bar maximum set to ", current_song_length)

    label_var.set(f"🎵 Now playing: {os.path.basename(song)}")
    wait_for_playing_and_update()
    check_song_end()
    tree.selection_set(tree.get_children()[current_index])

def pause_song():
    global paused
    if player:
        (player.play() if paused else player.pause())
        paused = not paused
        if not paused:
            wait_for_playing_and_update()

def stop_song():
    paused = False
    if player: player.stop()
    progress_bar['value'] = 0
    label_var.set("⏹ Stopped")
    time_label.config(text="")

def skip(step):
    global current_index
    current_index = (current_index + step) % len(playlist)
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
        if not paused and current_index < len(playlist) - 1:
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
    global player, current_index
    if player is not None:
        state = player.get_state()
        if state == vlc.State.Ended:
            progress_bar['value'] = 0
            time_label.config(text="")
            if not paused:
                if current_index < len(playlist) - 1:
                    skip(1)
                elif len(playlist) > 0:
                    current_index = 0
                    play_song()
                    # --- Ensure the first song is selected in the tree ---
                    first_item = tree.get_children()[0]
                    tree.selection_set(first_item)
                    tree.focus(first_item)
                    tree.see(first_item)
            return
    root.after(1000, check_song_end)

def delete_current_song():
    global player, current_index, current_index_playing

    sel = tree.selection()
    if not sel: return
    idx = tree.index(sel[0])
    if idx < 0 or idx >= len(playlist): return

    if player and current_index_playing == idx:
        stop_song()
        player = None

    del playlist[idx]
    tree.delete(sel[0])
    renumber_tree()

    if player:
        if current_index_playing >= idx:
            current_index_playing -= 1

    current_index = current_index_playing

    if playlist:
        tree.selection_set(tree.get_children()[current_index])
        tree.focus(tree.get_children()[current_index])
        tree.see(tree.get_children()[current_index])
    else:
        current_index = 0

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
root.title("🎵 MP3 Player")
root.geometry("720x580")
root.minsize(650, 500)
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

# === Load Folder Button ===
ttk.Button(btn2_frame, text="Add folder", command=lambda: add_folder(),
           ).grid(row=0, column=0, padx=2)

# === Add Songs Button ===
ttk.Button(btn2_frame, text="Add songs", command=lambda: add_songs(),
           ).grid(row=0, column=1, padx=2)

# === Clear Button ===
ttk.Button(btn2_frame, text="Delete", command=lambda: delete_current_song(),
           ).grid(row=0, column=2, padx=2)

# === Clear Button ===
ttk.Button(btn2_frame, text="Clear", command=lambda: clear_songs_list(),
           ).grid(row=0, column=3, padx=2)

# === Save Playlist Button ===
ttk.Button(btn2_frame, text="Save playlist as...", command=save_playlist_as,
           ).grid(row=0, column=4, padx=2)

# === Load Playlist Button ===
ttk.Button(btn2_frame, text="Load playlist...", command=load_playlist_from_file,
           ).grid(row=0, column=5, padx=2)

context_menu = tk.Menu(root, tearoff=0)
context_menu.add_command(label="Delete from list", command=lambda: delete_current_song())

#tree.bind("<Button-3>", show_context_menu)  # Right-click on Windows/Linux
tree.bind("<Control-Button-1>", show_context_menu)  # Ctrl+Click on Mac


# === Start ===
load_saved_playlist()
root.mainloop()
