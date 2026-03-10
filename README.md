# Mini Sync

Mini Sync is a lightweight, GUI-based Python application designed for file deployment and synchronization over SFTP. It allows you to connect to a remote server, browse local and remote directories side-by-side, and push changes between your local machine and the server using background observers or manual sync actions.

## ✨ Features

* **Simple GUI Interface:** Built with Tkinter for an easy-to-use, split-pane file browsing experience.
* **Secure SFTP Protocol:** Securely transfers files using Paramiko's `SSHClient` with automatic host key verification.
* **Two-Way Auto-Deploy:** Utilizes Watchdog to monitor local directories and background polling for remote directories. You can choose to automatically mirror changes from Local to Remote or Remote to Local.
* **Manual Synchronization:** Instantly sync entire directories in either direction with the click of a button.
* **Smart Syncing & Debouncing:** Built-in timers prevent the server from being spammed during rapid file-save sequences. The application also checks file modification timestamps to ensure only newer or altered files are overwritten.
* **Thread-Safe UI:** Network operations and file syncing run on background threads, ensuring the interface remains fast and responsive.
* **Activity Logging:** An embedded log console tracks all connection statuses, file uploads, and errors in real-time.

## 📋 Prerequisites

To run this application, you will need **Python 3.x** installed on your system along with a few external libraries. 

You can install the required dependencies using your terminal:

    pip install paramiko watchdog

*(Note: `tkinter` is included in the standard Python library, but on some Linux distributions, you may need to install it separately via your package manager, e.g., `sudo apt-get install python3-tk`).*

## 🚀 Usage


1. Run the script from your terminal:
    
    python deploy_window.py

2. **Connect to Server:** Verify or enter your server's IP, Port, Username, and Password in the top header, then click **Connect**.
3. **Select Local Path:** Click **Open Folder** on the left panel to choose the local directory you want to work from. Double-click folders to navigate.
4. **Select Remote Path:** Use the right panel to navigate to your target deployment folder on the server.
5. **Start Syncing:** * Click **Deploy Local → Remote** to watch your local folder and push changes to the server.
    * Click **Deploy Remote → Local** to poll the server and pull changes to your local machine.
    * Use the **Sync** buttons for an immediate, one-time directory overwrite.
6. Click **Stop Deploy** before disconnecting or closing the application.

## ⚠️ Important Considerations & Limitations

Mini Deploy is designed as a direct deployment pipeline. While it checks file timestamps to prevent redundant uploads, please be aware of the following:

* **Destructive Synchronization:** Syncing is destructive. If you delete a file on the source side, it will be deleted on the target side during a sync. Please ensure you have backups of your server data before initiating a sync.
* **No Workspace Verification:** The app will allow you to deploy any local folder into any remote folder. It does not check if the remote folder is already being used for something else. Always double-check your paths before starting a deployment.

## 📄 License

This project is open-source and available for personal or educational use.