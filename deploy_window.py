import tkinter as tk
from tkinter import messagebox, filedialog
import sys
import time
import os
import stat
import paramiko
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import queue

from dotenv import load_dotenv

load_dotenv()


class Deploy(FileSystemEventHandler):

    def __init__(self, sftp, local_path, remote_path, log_queue, sftp_lock, refresh_callback):

        super().__init__()

        self.sftp = sftp

        self.local_path = local_path

        self.remote_path = remote_path

        self.log_queue = log_queue

        self.sftp_lock = sftp_lock
        self.refresh_callback = refresh_callback

        self.timers = {}
        self.debounce_time = 1.0
        self.ignore_list = ['.git', '.DS_Store', '__pycache__', '.venv', 'node_modules', '.minisync']

    def is_ignored(self, path):
        """Checks if any part of the path is in the ignore list."""

        path_parts = path.replace("\\", "/").split("/")
        
        for ignored_item in self.ignore_list:
            if ignored_item in path_parts:
                return True
        return False



    def get_remote_path(self, local_path):

        relative_path = os.path.relpath(local_path, self.local_path)

        remote_path = os.path.join(self.remote_path, relative_path)

        return remote_path.replace("\\", "/")

    def create_remote_dir_r(self,remote_path):
        if remote_path=="/" or remote_path=="":
            return
        try:
            with self.sftp_lock:
                self.sftp.stat(remote_path)
        except IOError:
            self.create_remote_dir_r(os.path.dirname(remote_path))
            try:
                with self.sftp_lock:
                    self.sftp.mkdir(remote_path)
                self.log_queue.put(f"Created directory: {remote_path}")
            except:
                pass

    def on_created(self, event):

        """Handles creating files and folders to prevent duplicates."""

        if self.is_ignored(event.src_path):
            return
        
        try:
            remote_path = self.get_remote_path(event.src_path)

            if event.is_directory:
                self.create_remote_dir_r(os.path.dirname(remote_path))
                with self.sftp_lock:
                    self.sftp.mkdir(remote_path)
                    
                self.log_queue.put(f"Created: {remote_path}")
                
                self.refresh_callback()
            else:
                self.debounce_upload(event.src_path)
        except Exception as e:
            self.log_queue.put(f"Create Error: {e}")


    def on_modified(self, event):

        """Handles modifying files and folders to prevent duplicates."""


        if event.is_directory or self.is_ignored(event.src_path):

            return

        self.debounce_upload(event.src_path)


    def on_moved(self, event):

        """Handles renaming files and folders to prevent duplicates."""
        if self.is_ignored(event.src_path) or self.is_ignored(event.dest_path):
            return
        try:

            old_remote = self.get_remote_path(event.src_path)

            new_remote = self.get_remote_path(event.dest_path)

            with self.sftp_lock:
                self.sftp.rename(old_remote, new_remote)

            self.log_queue.put(f"Renamed: {os.path.basename(event.src_path)} -> {os.path.basename(event.dest_path)}")
            
            self.refresh_callback()

        except Exception as e:

            self.log_queue.put(f"Rename Error: {e}")



    def on_deleted(self, event):

        """Handles deleting files and folders on the remote server."""
        if self.is_ignored(event.src_path):
            return
        try:

            remote_path = self.get_remote_path(event.src_path)

            with self.sftp_lock:
                if event.is_directory:
                    self.sftp.rmdir(remote_path)
                    self.log_queue.put(f"Deleted Folder: {remote_path}")
                else:
                    self.sftp.remove(remote_path)
                    self.log_queue.put(f"Deleted File: {remote_path}")
            
            self.refresh_callback()

        except Exception as e:

            self.log_queue.put(f"Delete Error: {e}")


    def debounce_upload(self, new_path):
        if new_path in self.timers:
            self.timers[new_path].cancel()
        timer = threading.Timer(self.debounce_time, self.process_upload, args=[new_path])
        self.timers[new_path] = timer
        timer.start()

    def process_upload(self, new_path):
        if new_path in self.timers:
            del self.timers[new_path]
        try:
            remote_path = self.get_remote_path(new_path)
            self.create_remote_dir_r(os.path.dirname(remote_path))
            with self.sftp_lock:
                self.sftp.put(new_path, remote_path)
            self.log_queue.put(f"Modified: {os.path.basename(new_path)}") 
            self.refresh_callback()        
        except Exception as e:
            self.log_queue.put(f"Upload Error: {e}")



class window(FileSystemEventHandler):
    def __init__(self, root):
        self.root = root
        self.root.title("Mini Deploy")
        self.root.minsize(800, 500)

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.main_frame = tk.Frame(root, padx=10, pady=10)
        self.main_frame.grid(row=0, column=0, sticky="nsew")

        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=0)
        self.main_frame.grid_rowconfigure(1, weight=1)

        # --- 1. HEADER SECTION ---
        self.header = tk.Frame(
            self.main_frame, 
            padx=10, 
            pady=10, 
            relief="groove", 
            borderwidth=2
        )

        self.header.grid(row=0, column=0, columnspan=2, sticky="nw", pady=(0, 10))

        tk.Label(self.header, text="IP:").grid(row=0, column=0, sticky="w")
        self.ip = tk.Entry(self.header, width=12)
        self.ip.grid(row=0, column=1, padx=5)

        tk.Label(self.header, text="Port:").grid(row=0, column=2, sticky="w")
        self.port = tk.Entry(self.header, width=12)
        self.port.grid(row=0, column=3, padx=5)

        tk.Label(self.header, text="User:").grid(row=0, column=4, sticky="w")
        self.user = tk.Entry(self.header, width=12)
        self.user.grid(row=0, column=5, padx=5)

        tk.Label(self.header, text="Password:").grid(row=0, column=6, sticky="w")
        self.passw = tk.Entry(self.header, show="*", width=12)
        self.passw.grid(row=0, column=7, padx=5)

        self.connect = tk.Button(self.header, text="Connect", command=self.start_connect)
        self.connect.grid(row=0, column=8, padx=10)

        self.disconnect = tk.Button(self.header, text="Disconnect", command=self.end_connect, state="disabled")
        self.disconnect.grid(row=0, column=9, padx=10)

# --- 2. LOCAL FILE VIEWER (Left Side) ---
        self.local_container = tk.Frame(self.main_frame)
        self.local_container.grid(row=1, column=0, sticky="nsew", padx=(0, 5))

        self.local_container.grid_columnconfigure(0, weight=1) 
        self.local_container.grid_rowconfigure(1, weight=1) 

        self.local_path_label = tk.Label(self.local_container, text="Local Path:", font=('Arial', 10, 'bold'))
        self.local_path_label.grid(row=0, column=0, columnspan=2, sticky="w")

        self.local_action_btn = tk.Button(self.local_container, text="Open Folder", command=self.open_folder)
        self.local_action_btn.grid(row=0, column=1, sticky="e", pady=(0, 5))

        self.local_fileviewer = tk.Listbox(self.local_container)
        self.local_fileviewer.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.local_fileviewer.bind('<Double-1>', self.on_local_double_click)



        # --- 3. REMOTE FILE VIEWER (Right Side) ---
        self.remote_container = tk.Frame(self.main_frame)
        self.remote_container.grid(row=1, column=1, sticky="nsew", padx=(5, 0))

        self.remote_container.grid_columnconfigure(0, weight=1)
        self.remote_container.grid_rowconfigure(1, weight=1)

        self.remote_path_label = tk.Label(self.remote_container, text="Remote Path:", font=('Arial', 10, 'bold'))
        self.remote_path_label.grid(row=0, column=0, sticky="w")

        self.remote_action_btn = tk.Button(self.remote_container, text="Refresh", command=self.refresh_files)
        self.remote_action_btn.grid(row=0, column=1, sticky="e", pady=(0, 5))

        self.fileviewer = tk.Listbox(self.remote_container)
        self.fileviewer.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.fileviewer.bind('<Double-1>', self.on_remote_double_click)

        # --- 4. AUTO DEPLOYMENT ---
        self.deployment_container = tk.Frame(self.main_frame)
        self.deployment_container.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(10, 0))

        self.deployment_container.grid_columnconfigure(0, weight=1)
        self.deployment_container.grid_rowconfigure(1, weight=1)

        self.deploy_btn = tk.Button(self.deployment_container, text="Auto Deploy", command=self.start_observer)
        self.deploy_btn.grid(row=0, column=0, sticky="e") # Sticky west to keep it left-aligned

        self.log = tk.Listbox(self.deployment_container)
        self.log.grid(row=1, column=0, sticky="nsew")

        # --- 5. Paths and Other Stuff---
        self.current_remote_path = "."
        self.current_local_path = None
        self.is_deploying = False
        self.lockables = [self.connect, self.disconnect]
        self.sftp = None
        self.sftp_lock = threading.Lock()
        self.ignore_list = ['.git', '.DS_Store', '__pycache__', '.venv', 'node_modules', '.minisync']


        # --- 6. Log Queue---
        self.log_queue = queue.Queue()
        self.poll_log_queue()

    def poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log.insert(0,msg)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_log_queue)

    def start_connect(self):
        if self.sftp:
            self.log_queue.put("Already connected to a server.")
            return
        self.disconnect.config(state="normal")

        threading.Thread(target=self._connect_thread, daemon=True).start()
    
    def _connect_thread(self):
        if not self.ip.get() or not self.port.get() or not self.user.get() or not self.passw.get():
            self.log_queue.put("Connection Error: All fields are required.")
            self.root.after(0, lambda: self.connect.config(state="normal"))
            return
        self.HOST = self.ip.get()
        self.PORT = int(self.port.get())
        self.USERNAME = self.user.get()
        self.PASSWORD = self.passw.get()
        self.ssh = None
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.load_system_host_keys()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(hostname=self.HOST,port=self.PORT, username=self.USERNAME, password=self.PASSWORD)
            self.sftp = self.ssh.open_sftp()
            self.log_queue.put("Connected successfully!")
            self.root.after(0, self._on_connect_success)
        except Exception as e:
            self.log_queue.put(f"Connection Error: {e}")
            self.root.after(0, lambda: self.connect.config(state="normal"))

    def _on_connect_success(self):
        self.disconnect.config(state="normal")
        self.refresh_remote_files()

    def end_connect(self):
        if self.is_deploying:
            self.closing()
        if self.sftp:
            self.disconnect.config(state="disabled")
            self.sftp.close()
            if self.ssh:
                self.ssh.close()
            self.sftp = None
            self.ssh = None
            self.current_remote_path = "."
            self.log_queue.put("Disconnected")

    def open_folder(self):
        if self.is_deploying:
            self.log_queue.put("Stop deployment before changing folders!")
        selected_directory = filedialog.askdirectory(
            initialdir="/", 
            title="Select Local Directory"
        )
        
        if selected_directory:
            self.log_queue.put(f"New Local Path: {selected_directory}")
            self.current_local_path = selected_directory
            self.refresh_local_files(self.current_local_path)
    
    def refresh_files(self):
        self.refresh_local_files(self.current_local_path)
        self.refresh_remote_files()
    
    def refresh_local_files(self, path):
        if not self.current_local_path:
            return
        try:
            path = os.path.abspath(path)
            items = os.listdir(path)
            self.local_fileviewer.delete(0, tk.END)
            if os.path.dirname(path) != path:
                self.local_fileviewer.insert(tk.END, "    ../")
            for item in items:
                prefix = "[D] " if os.path.isdir(os.path.join(path, item)) else "[F] "
                self.local_fileviewer.insert(tk.END, prefix + item)
                
            self.local_path_label.config(text=f"Local Path: {path}")
        except Exception as e:
            self.log_queue.put(f"Error reading directory: {e}")
            self.current_local_path = os.path.dirname(self.current_local_path)


    def refresh_remote_files(self):
        if not self.current_remote_path:
            return
        if self.sftp:
            try:
                with self.sftp_lock:
                    items = self.sftp.listdir_attr(self.current_remote_path)
                self.fileviewer.delete(0,tk.END)
                if self.current_remote_path != ".":
                    self.fileviewer.insert(tk.END, "    ../")
                for item in items:
                    prefix = "[D] " if stat.S_ISDIR(item.st_mode) else "[F] "
                    self.fileviewer.insert(tk.END, prefix + item.filename)
                self.remote_path_label.config(text=f"Local Path: {self.current_remote_path}")
            except Exception as e:
                self.log_queue.put(f"Could not list directory {self.current_remote_path}: {e}")
                self.current_remote_path = os.path.dirname(self.current_remote_path)

        
    def on_local_double_click(self, event):
        if not self.local_fileviewer.curselection() or self.is_deploying:
            return
        selection = self.local_fileviewer.get(self.local_fileviewer.curselection())
        name = selection[4:]
        if selection.startswith("[D]"):
            new_path = os.path.join(self.current_local_path, name).replace("\\", "/")
            if os.access(new_path, os.R_OK):
                self.current_local_path = new_path
                self.refresh_local_files(self.current_local_path)
            else:
                messagebox.showwarning("Access Denied", f"No permission to access: {name}")
                self.log_queue.put(f"Error: Permission denied for {new_path}")
        elif name == "../":
            self.current_local_path = os.path.dirname(self.current_local_path)
            if not self.current_local_path or self.current_local_path == ".":
                self.current_local_path = "."
            self.refresh_local_files(self.current_local_path)
        else:
            return

    def on_remote_double_click(self, event):
        if not self.fileviewer.curselection() or self.is_deploying:
            return
        selection = self.fileviewer.get(self.fileviewer.curselection())
        name = selection[4:]
        if selection.startswith("[D]"):
            target_path = os.path.join(self.current_remote_path, name).replace("\\", "/")
            try:
                self.sftp.listdir(target_path)
                self.current_remote_path = target_path
                self.refresh_remote_files()
            except IOError:
                messagebox.showwarning("Access Denied", "Remote permission denied or folder missing.")
                self.log_queue.put(f"Remote Error: Cannot access {target_path}")
        elif name == "../":
            self.current_remote_path = os.path.dirname(self.current_remote_path)
            if not self.current_remote_path or self.current_remote_path == ".":
                self.current_remote_path = "."
            self.refresh_remote_files()
        else:
            return
    
    def get_remote_path(self, local_path):

        relative_path = os.path.relpath(local_path, self.current_local_path)

        remote_path = os.path.join(self.current_remote_path, relative_path)

        return remote_path.replace("\\", "/")

    def is_ignored(self, path):
        """Checks if any part of the path is in the ignore list."""

        path_parts = path.replace("\\", "/").split("/")
        
        for ignored_item in self.ignore_list:
            if ignored_item in path_parts:
                return True
        return False

    def search_push_local(self,local_dir):
        try:
            for item in os.listdir(local_dir):
                if self.is_ignored(item):
                    continue

                local_item_path = os.path.join(local_dir, item).replace("\\", "/")
                remote_item_path = self.get_remote_path(local_item_path)

                if os.path.isdir(local_item_path):
                    try:
                        self.sftp.stat(remote_item_path)
                    except:
                        with self.sftp_lock:
                            self.sftp.mkdir(remote_item_path)
                        self.log_queue.put(f"Created remote folder: {remote_item_path}")
                    self.search_push_local(local_item_path)
                else:
                    local_time = int(os.path.getmtime(local_item_path))
                    needs_upload = False

                    try:
                        remote_time = self.sftp.stat(remote_item_path).st_mtime
                        if local_time > remote_time:
                            needs_upload = True
                    except IOError:
                        needs_upload = True
                    
                    if needs_upload:
                        with self.sftp_lock:
                            self.sftp.put(local_item_path,remote_item_path)
                            self.sftp.utime(remote_item_path, (local_time, local_time))
                        self.log_queue.put(f"Pushed offline update: {item}")
        except Exception as e:
            self.log_queue.put(f"Initial Push Error: {e}")

    def start_full_deploy(self):
        self.log_queue.put("Pushing offline updates...")
        self.search_push_local(self.current_local_path)
        self.root.after(0, self.start_watchdog)

    def start_observer(self):
        if not self.sftp:
            self.log_queue.put(f"Connection not established.")
            return
        if not self.current_local_path or not self.current_remote_path:
            self.log_queue.put(f"Directories not chosen.")
            return
        self.deploy_btn.config(text="Stop Deploy",command=self.closing)
        self.connect.config(state="disabled")
        self.disconnect.config(state="disabled")
        self.local_action_btn.config(state="disabled")
        self.remote_action_btn.config(state="disabled")
        self.is_deploying = True
        threading.Thread(target=self.start_full_deploy, daemon=True).start()

    def start_watchdog(self):
        self.log_queue.put(f"Watching for changes...")
        safe_refresh = lambda: self.root.after(0, self.refresh_files)
        self.observer = Observer()
        self.observer.schedule(Deploy(self.sftp, self.current_local_path,self.current_remote_path,self.log_queue, self.sftp_lock, safe_refresh), self.current_local_path, recursive=True)
        self.observer.start()

    def closing(self):
        if self.observer or self.is_deploying:
            self.connect.config(state="normal")
            self.disconnect.config(state="normal")
            self.local_action_btn.config(state="normal")
            self.remote_action_btn.config(state="normal")
            self.observer.stop()
            self.observer.join()
            self.deploy_btn.config(text = "Auto Deploy",command = self.start_observer)
            self.log_queue.put("Stopped Deployment")
            self.is_deploying = False
            self.observer = None
        
if __name__ == "__main__":
    root = tk.Tk()
    my_app = window(root)
    # ==========================================
    # --- SAFE DEBUG DEFAULTS ---
    # ==========================================
    
    # Safely pull credentials from the local .env file. 
    # The second argument (e.g., "") is a fallback just in case the .env file is missing.
    my_app.ip.insert(0, os.getenv("TEST_IP", "127.0.0.1"))
    my_app.port.insert(0, os.getenv("TEST_PORT", "22"))
    my_app.user.insert(0, os.getenv("TEST_USER", ""))
    my_app.passw.insert(0, os.getenv("TEST_PASS", "")) 

    my_app.current_local_path = os.getenv("TEST_LOCAL_PATH", ".")
    my_app.current_remote_path = os.getenv("TEST_REMOTE_PATH", ".")

    # Force the left-side listbox to load the local path immediately
    if my_app.current_local_path != ".":
        my_app.refresh_local_files(my_app.current_local_path)
    
    # ==========================================
    root.mainloop()
