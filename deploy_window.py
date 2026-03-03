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


class Deploy(FileSystemEventHandler):

    def __init__(self, sftp, local_path, remote_path, log_queue):

        super().__init__()

        self.sftp = sftp

        self.local_path = local_path

        self.remote_path = remote_path

        self.log_queue = log_queue

        self.timers = {}
        self.debounce_time = 1.0



    def get_remote_path(self, local_path):

        relative_path = os.path.relpath(local_path, self.local_path)

        remote_path = os.path.join(self.remote_path, relative_path)

        return remote_path.replace("\\", "/")

    def create_remote_dir_r(self,remote_path):
        if remote_path=="/" or remote_path=="":
            return
        try:
            self.sftp.stat(remote_path)
        except IOError:
            self.create_remote_dir_r(os.path.dirname(remote_path))
            try:
                self.sftp.mkdir(remote_path)
                self.log_queue.put(f"Created directory: {remote_path}")
            except:
                pass

    def on_created(self, event):

        """Handles creating files and folders to prevent duplicates."""

        if ".DS_Store" in event.src_path or "tmp" in event.src_path:
            return
        
        try:
            remote_path = self.get_remote_path(event.src_path)

            if event.is_directory:
                self.create_remote_dir_r(os.path.dirname(remote_path))
                self.sftp.mkdir(remote_path)
                self.log_queue.put(f"Created: {remote_path}")
            else:
                self.debounce_upload(event.src_path)
        except Exception as e:
            self.log_queue.put(f"Create Error: {e}")


    def on_modified(self, event):

        """Handles modifying files and folders to prevent duplicates."""


        if event.is_directory or ".DS_Store" in event.src_path or "tmp" in event.src_path:

            return

        self.debounce_upload(event.src_path)


    def on_moved(self, event):

        """Handles renaming files and folders to prevent duplicates."""

        try:

            old_remote = self.get_remote_path(event.src_path)

            new_remote = self.get_remote_path(event.dest_path)

           

            self.sftp.rename(old_remote, new_remote)

            self.log_queue.put(f"Renamed: {os.path.basename(event.src_path)} -> {os.path.basename(event.dest_path)}")

        except Exception as e:

            self.log_queue.put(f"Rename Error: {e}")



    def on_deleted(self, event):

        """Handles deleting files and folders on the remote server."""

        try:

            remote_path = self.get_remote_path(event.src_path)

           

            if event.is_directory:

                self.sftp.rmdir(remote_path)

                self.log_queue.put(f"Deleted Folder: {remote_path}")

            else:

                self.sftp.remove(remote_path)

                self.log_queue.put(f"Deleted File: {remote_path}")

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
            self.sftp.put(new_path, remote_path)
            self.log_queue.put(f"Modified: {os.path.basename(new_path)}")         
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


    def start_observer(self):
        if not self.sftp:
            self.log_queue.put(f"Connection not established.")
            return
        if not self.current_local_path or not self.current_remote_path:
            self.log_queue.put(f"Directories not chosen.")
            return
        try:
            self.sftp.stat(self.current_remote_path+"/.minisync")
        except IOError:
            answer = messagebox.askyesno(title="Add Synchronization?", message="This remote directory is currently not initialized for syncing. Would you like to initialize it?")
            if answer:
                self.sftp.open(self.current_remote_path+"/.minisync", 'w')
                self.log_queue.put(f"Directory initialized")
            else:
                self.log_queue.put(f"Deployment failed")
                return
        self.deploy_btn.config(text="Stop Deploy",command=self.closing)
        self.connect.config(state="disabled")
        self.disconnect.config(state="disabled")
        self.is_deploying = True
        self.log_queue.put(f"Watching for changes...")
        self.observer = Observer()
        self.observer.schedule(Deploy(self.sftp, self.current_local_path,self.current_remote_path,self.log_queue), self.current_local_path, recursive=True)
        self.observer.start()

    def closing(self):
        if self.observer or self.is_deploying:
            self.connect.config(state="normal")
            self.disconnect.config(state="normal")
            self.observer.stop()
            self.observer.join()
            self.deploy_btn.config(text = "Auto Deploy",command = self.start_observer)
            self.log_queue.put("Stopped Deployment")
            self.is_deploying = False
            self.observer = None
        


        
if __name__ == "__main__":
    root = tk.Tk()
    my_app = window(root)
    root.mainloop()
