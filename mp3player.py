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
    tree.insert("", "end", values=(title, artist, f"{dur//60:02}:{dur%60:02}"))
    
def add_folder():
    folder = filedialog.askdirectory()
    if not folder: return
    playlist.clear(); tree.delete(*tree.get_children())
    for file in sorted(os.listdir(folder)):
        supported_ext = (".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".wma")
        if file.lower().endswith(supported_ext):
            path = os.path.join(folder, file)
            add_song_to_list(path)
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
    song_tmp = filedialog.askopenfilenames(title="Select Audio Files",
                                           filetypes=[("Audio Files", "*.mp3 *.wav *.flac *.ogg *.aac *.m4a *.wma"),
                                                      ("All Files", "*.*")])
    if not song_tmp: return
    #playlist.clear(); tree.delete(*tree.get_children())
    for file in sorted(song_tmp):
        supported_ext = (".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".wma")
        if file.lower().endswith(supported_ext):
            #path = os.path.join(folder, file)
            add_song_to_list(file)
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
    global player
    if player is not None:
        state = player.get_state()
        if state == vlc.State.Ended:
            progress_bar['value'] = 0
            time_label.config(text="")
            if not paused and current_index < len(playlist) - 1:
                skip(1)
            return
    root.after(1000, check_song_end)

PLAYLIST_FILE = "last_playlist.json"
playlist, current_index, paused, player, current_song_length = [], 0, False, None, 0

# === Setup GUI ===
root = tk.Tk()
root.title("🎵 MP3 Player")
root.geometry("720x580")
root.minsize(650, 500)
root.configure(bg="#2c2c2c")

# === Fonts and Colors ===
font_main = ("Segoe UI", 11)
bg_main = "#2c2c2c"
fg_main = "#808080"
btn_color = "#3a3a3a"

# === Treeview ===
tree_frame = tk.Frame(root, bg=bg_main)
tree_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(10, 5))

columns = ("Title", "Artist", "Duration")
tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
for col in columns:
    tree.heading(col, text=col)
tree.column("Title", width=300)
tree.column("Artist", width=280)
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
tk.Label(root, textvariable=label_var, font=font_main, fg=fg_main, bg=bg_main).pack(pady=(5, 5))

# === Progress + Time ===
progress_bar = ttk.Progressbar(root, orient="horizontal", length=600, mode="determinate")
progress_bar.pack(pady=4)
progress_bar.bind("<Button-1>", lambda e: seek_progress(e))

time_label = tk.Label(root, text="", font=font_main, fg=fg_main, bg=bg_main)
time_label.pack()

# === Buttons ===
btn_frame = tk.Frame(root, bg=bg_main)
btn_frame.pack(pady=12)

def add_btn(txt, cmd, col): 
    tk.Button(btn_frame, text=txt, font=font_main, command=cmd, width=5, bg=btn_color, fg=fg_main, relief=tk.FLAT)\
        .grid(row=0, column=col, padx=6)

add_btn("Prev", lambda: skip(-1), 0)
add_btn("Play", play_selected, 1)
add_btn("Pause", pause_song, 2)
add_btn("Stop", stop_song, 3)
add_btn("Next", lambda: skip(1), 4)

# === Volume Slider with 0–150% and % Display ===
vol_frame = tk.Frame(root, bg=bg_main)
vol_frame.pack(pady=5)

tk.Label(vol_frame, text="Volume", font=font_main, bg=bg_main, fg=fg_main).pack(side=tk.LEFT)

volume_percent = tk.StringVar(value="100%")  # Default: 100%

def on_volume_change(val):
    percent = int(float(val))
    volume_percent.set(f"{percent}%")
    if player:
        player.audio_set_volume(min(percent, 150))  # VLC max = 150

volume_slider = tk.Scale(vol_frame, from_=0, to=150, orient=tk.HORIZONTAL, resolution=1,
                         command=on_volume_change, bg=bg_main, fg=fg_main,
                         troughcolor="#555", highlightthickness=0, sliderlength=15, width=10,
                         showvalue=0, length=150)
volume_slider.set(100)  # Default value
volume_slider.pack(side=tk.LEFT, padx=8)

tk.Label(vol_frame, textvariable=volume_percent, font=font_main, bg=bg_main, fg=fg_main).pack(side=tk.LEFT, padx=6)

# === Buttons ===
btn2_frame = tk.Frame(root, bg=bg_main)
btn2_frame.pack(pady=12)

# === Load Folder Button ===
tk.Button(btn2_frame, text="Add folder", command=lambda: add_folder(), font=font_main,
          bg=btn_color, fg=fg_main, padx=6, pady=2, relief=tk.FLAT).grid(row=0, column=0, padx=2)

# === Add Songs Button ===
tk.Button(btn2_frame, text="Add songs", command=lambda: add_songs(), font=font_main,
          bg=btn_color, fg=fg_main, padx=6, pady=2, relief=tk.FLAT).grid(row=0, column=1, padx=2)

# === Clear Button ===
tk.Button(btn2_frame, text="Clear", command=lambda: clear_songs_list(), font=font_main,
          bg=btn_color, fg=fg_main, padx=6, pady=2, relief=tk.FLAT).grid(row=0, column=2, padx=2)


# === Start ===
load_saved_playlist()
root.mainloop()
