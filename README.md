---

# Screen-Time-Tracker

A robust, Python-based screen time tracking application designed to monitor activity, analyze usage patterns, and sync data seamlessly to the cloud.

## 🚀 Features

* **Activity Tracking:** Accurately monitors active window usage and logs screen time (`tracker.py`).
* **Analytics Dashboard:** Generates insights into your daily digital habits and productivity (`analytics.py`).
* **Cloud Synchronization:** Built-in support for syncing local tracking data to a Supabase backend (`cloud_sync.py`, `supabase_setup.sql`).
* **Web Interface:** Includes an HTML frontend for viewing statistics, accessible via the Vercel deployment (`index.html`).
* **Windows Executable:** Ready-to-compile batch scripts to bundle the application into a stealthy, standalone Windows executable (`compile.bat`, `.spec` files).

## 🛠️ Prerequisites

* Python 3.x
* Supabase account (for cloud database synchronization)
* Windows OS (for the compiled executable features and specific Windows API tracking)

## 📦 Installation & Setup

1. **Clone the repository:**
```bash
git clone https://github.com/Gethubmaxer/Screen-Time-Tracker.git
cd Screen-Time-Tracker

```


2. **Install dependencies:**
```bash
pip install -r requirements.txt

```


3. **Database Configuration:**
* Create a new project in Supabase.
* Execute the `supabase_setup.sql` script in your Supabase SQL editor to initialize the required tables.
* Update `config.py` with your Supabase URL and API keys.



## 💻 Usage

To run the tracker locally from the source code:

```bash
python main.py

```

### Compiling for Windows

If you want to run the tracker as a background process or standalone app, you can build the executable using the provided build scripts and specifications (e.g., `RuntimeBrokerX64.spec` for a disguised background process).

Run the included batch script from your terminal:

```cmd
compile.bat

```

## 🗂️ Core Project Structure

* `main.py`: The main application entry point.
* `tracker.py`: Core logic for hooking into the OS to monitor active windows.
* `database.py` & `cloud_sync.py`: Local database management and remote Supabase syncing logic.
* `analytics.py`: Data processing and formatting for usage insights.
* `index.html`: The web view/dashboard for rendering your statistics.
* `compile.bat` / `compile.py`: Build tools for creating the deployment executable using PyInstaller.

---
