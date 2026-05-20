import re
import subprocess
import sys
import os

def main():
    exe_name = "RuntimeBrokerX64"
    current_version = None
    compiled_version = None

    try:
        with open("main.py", "r", encoding="utf-8") as f:
            content = f.read()

        # Extract EXE name
        match = re.search(r'APP_EXE_NAME\s*=\s*"(.*?)"', content)
        if match:
            exe_name = match.group(1)
            print(f"Found EXE name in main.py: {exe_name}")
        else:
            print("Could not find APP_EXE_NAME in main.py, using default.")

        # Extract and prompt for version
        ver_match = re.search(r'CURRENT_VERSION\s*=\s*"(.*?)"', content)
        if ver_match:
            current_version = ver_match.group(1)
            parts = current_version.split(".")
            default_ver = f"{parts[0]}.{parts[1]}.{int(parts[-1]) + 1}" if len(parts) >= 3 else "1.0.1"
            try:
                prompt = input(f"Enter version (default: {default_ver}): ").strip()
            except (EOFError, OSError):
                prompt = ""
            new_version = prompt if prompt else default_ver
            content = content.replace(
                f'CURRENT_VERSION = "{current_version}"',
                f'CURRENT_VERSION = "{new_version}"',
            )
            with open("main.py", "w", encoding="utf-8") as f:
                f.write(content)
            compiled_version = new_version
            print(f"Version set to: {new_version}")
        else:
            print("Version: not found (add CURRENT_VERSION to main.py)")
    except Exception as e:
        print(f"Error reading main.py: {e}")

    # Find PyInstaller in venv
    venv_python = os.path.join(os.path.dirname(__file__), "venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        print("ERROR: Virtual environment not found at venv/Scripts/python.exe")
        print("Run: python -m venv venv && venv\\Scripts\\pip install PySide6 pyinstaller")
        sys.exit(1)

    pyinstaller = os.path.join(os.path.dirname(__file__), "venv", "Scripts", "pyinstaller.exe")
    if not os.path.exists(pyinstaller):
        print("ERROR: PyInstaller not found in venv. Run: venv\\Scripts\\pip install pyinstaller")
        sys.exit(1)

    print(f"Using PyInstaller from venv: {pyinstaller}")
    print("Compiling executable...")

    # Clean previous builds
    for d in ["build", "dist"]:
        dp = os.path.join(os.path.dirname(__file__), d)
        if os.path.exists(dp):
            import shutil
            shutil.rmtree(dp, ignore_errors=True)

    # Remove old spec file
    spec_path = os.path.join(os.path.dirname(__file__), "RuntimeBrokerX64.spec")
    if os.path.exists(spec_path):
        os.remove(spec_path)
    spec_path = os.path.join(os.path.dirname(__file__), f"{exe_name}.spec")
    if os.path.exists(spec_path):
        os.remove(spec_path)

    cmd = [
        pyinstaller,
        "--noconsole",
        "--onefile",
        "--windowed",
        "--clean",
        f"--name={exe_name}",
        "--hidden-import=cloud_sync",
        "--hidden-import=config",
        "main.py"
    ]

    result = subprocess.run(cmd, cwd=os.path.dirname(__file__))

    if result.returncode == 0:
        dist_dir = os.path.join(os.path.dirname(__file__), "dist")
        files = os.listdir(dist_dir)
        print("\nCompilation successful!")
        print(f"   Version: {compiled_version or 'unknown'}")
        for f in files:
            size = os.path.getsize(os.path.join(dist_dir, f))
            print(f"   {f}  ({size / 1024 / 1024:.1f} MB)")
    else:
        print("\nCompilation failed.")


if __name__ == "__main__":
    main()
