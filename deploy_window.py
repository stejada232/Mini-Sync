import tkinter as tk
from tkinter import messagebox, filedialog
import sys
import time
import os
import stat
import paramiko
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class Deploy(FileSystemEventHandler):

    def __init__(self, sftp, local_path, remote_path, log):

        super().__init__()

        self.sftp = sftp

        self.local_path = local_path

        self.remote_path = remote_path

        self.log = log



    def get_remote_path(self, local_path):

        relative_path = os.path.relpath(local_path, self.local_path)

        remote_path = os.path.join(self.remote_path, relative_path)

        return remote_path.replace("\\", "/")



    def on_modified(self, event):

        if event.is_directory or ".DS_Store" in event.src_path or "tmp" in event.src_path:

            return

        self.log.insert(0, f"Modified: {os.path.basename(event.src_path)}")

        self.process_upload(event.src_path)



    def on_moved(self, event):

        """Handles renaming files and folders to prevent duplicates."""

        try:

            old_remote = self.get_remote_path(event.src_path)

            new_remote = self.get_remote_path(event.dest_path)

           

            self.sftp.rename(old_remote, new_remote)

            self.log.insert(0, f"Renamed: {os.path.basename(event.src_path)} -> {os.path.basename(event.dest_path)}")

        except Exception as e:

            self.log.insert(0, f"Rename Error: {e}")



    def on_deleted(self, event):

        """Handles deleting files and folders on the remote server."""

        try:

            remote_path = self.get_remote_path(event.src_path)

           

            if event.is_directory:

                self.sftp.rmdir(remote_path)

                self.log.insert(0, f"Deleted Folder: {remote_path}")

            else:

                self.sftp.remove(remote_path)

                self.log.insert(0, f"Deleted File: {remote_path}")

        except Exception as e:

            self.log.insert(0, f"Delete Error: {e}")



    def process_upload(self, new_path):

        try:
            remote_path = self.get_remote_path(new_path)
            self.sftp.put(new_path, remote_path)
            self.log.insert(0, f"Uploaded: {remote_path}")            
        except Exception as e:
            self.log.insert(0, f"Upload Error: {e}")



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

        self.pathLabel = tk.Label(self.remote_container, text="Remote Path:", font=('Arial', 10, 'bold'))
        self.pathLabel.grid(row=0, column=0, sticky="w")

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
        self.current_local_path = "."
        self.is_deploying = False
        self.lockables = [self.connect, self.disconnect]
        self.sftp = None
    
    def start_connect(self):
        self.disconnect.config(state="normal")
        self.HOST = self.ip.get()
        self.PORT = int(self.port.get())
        self.USERNAME = self.user.get()
        self.PASSWORD = self.passw.get()
        self.transport = None
        try:
            self.transport = paramiko.Transport((self.HOST, self.PORT))
            self.transport.connect(username=self.USERNAME, password=self.PASSWORD)
            self.sftp = paramiko.SFTPClient.from_transport(self.transport)
            self.refresh_remote_files()
        except Exception as e:
            self.log.insert(0,f"Error: {e}")
    
    def end_connect(self):
        if self.sftp:
            self.disconnect.config(state="disabled")
            self.sftp.close()
            self.transport.close()
            self.sftp = None

    def open_folder(self):
        selected_directory = filedialog.askdirectory(
            initialdir="/", 
            title="Select Local Directory"
        )
        
        if selected_directory:
            self.log.insert(0,f"New Local Path: {selected_directory}")
            self.current_local_path = selected_directory
            self.refresh_local_files(self.current_local_path)
    
    def refresh_files(self):
        self.refresh_local_files(self.current_local_path)
        self.refresh_remote_files()
    
    def refresh_local_files(self, path):
        try:
            items = os.listdir(path)
            self.local_fileviewer.delete(0, tk.END)
            if path != "C:/":
                self.local_fileviewer.insert(tk.END, "    ../")
            for item in items:
                prefix = "[D] " if os.path.isdir(os.path.join(path, item)) else "[F] "
                self.local_fileviewer.insert(tk.END, prefix + item)
                
            self.local_path_label.config(text=f"Local Path: {path}")
        except Exception as e:
            self.log.insert(0,f"Error reading directory: {e}")
            self.current_local_path = os.path.dirname(self.current_local_path)


    def refresh_remote_files(self):
        if self.sftp:
            try:
                items = self.sftp.listdir_attr(self.current_remote_path)
                self.fileviewer.delete(0,tk.END)
                if self.current_remote_path != ".":
                    self.fileviewer.insert(tk.END, "    ../")
                for item in items:
                    prefix = "[D] " if stat.S_ISDIR(item.st_mode) else "[F] "
                    self.fileviewer.insert(tk.END, prefix + item.filename)
            except Exception as e:
                self.log.insert(0, f"Could not list directory {self.current_remote_path}: {e}")
                self.current_remote_path = os.path.dirname(self.current_remote_path)

        
    def on_local_double_click(self, event):
        if not self.local_fileviewer.curselection():
            return
        print(self.current_local_path)
        selection = self.local_fileviewer.get(self.local_fileviewer.curselection())
        name = selection[4:]
        if selection.startswith("[D]"):
            new_path = os.path.join(self.current_local_path, name).replace("\\", "/")
            if os.access(new_path, os.R_OK):
                self.current_local_path = new_path
                self.refresh_local_files(self.current_local_path)
            else:
                messagebox.showwarning("Access Denied", f"No permission to access: {name}")
                self.log.insert(0, f"Error: Permission denied for {new_path}")
        elif name == "  ../":
            self.current_local_path = os.path.dirname(self.current_local_path)
            if not self.current_local_path or self.current_local_path == ".":
                self.current_local_path = "."
            self.refresh_local_files(self.current_local_path)
        else:
            return

    def on_remote_double_click(self, event):
        if not self.fileviewer.curselection():
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
                self.log.insert(0, f"Remote Error: Cannot access {target_path}")
        elif name == "../":
            self.current_remote_path = os.path.dirname(self.current_remote_path)
            if not self.current_remote_path or self.current_remote_path == ".":
                self.current_remote_path = "."
            self.refresh_remote_files()
        else:
            return

    def start_observer(self):
        self.deploy_btn.config(text="Stop Deploy",command=self.closing)
        self.connect.config(state="disabled")
        self.disconnect.config(state="disabled")
        self.is_deploying = True
        self.log.insert(0,f"Watching for changes...")
        self.observer = Observer()
        self.observer.schedule(Deploy(self.sftp, self.current_local_path,self.current_remote_path,self.log), self.current_local_path, recursive=True)
        self.observer.start()

    def closing(self):
        if self.observer or self.is_deploying:
            self.connect.config(state="normal")
            self.disconnect.config(state="normal")
            self.observer.stop()
            self.observer.join()
            self.deploy_btn.config(text = "Auto Deploy",command = self.start_observer)
            self.is_deploying = False
            self.observer = None
        

        
        
if __name__ == "__main__":
    root = tk.Tk()
    my_app = window(root)
    root.mainloop()
