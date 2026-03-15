import os

# Default extensions for file scanning
_DEFAULT_EXTENSIONS = ['.txt', '.json', '.csv', '.toml', '.ini', '.cfg', '.conf', '.log', '.rst', '.ts', '.js', '.css', '.html']

# Function to find all files in a directory, excluding specified directories

def find_files(root_directory):
    found_files = []
    for dirpath, dirnames, filenames in os.walk(root_directory):
        if '__pycache__' in dirnames:
            dirnames.remove('__pycache__')  # Exclude __pycache__ directories
        if '.ironmate_venv' in dirnames:
            dirnames.remove('.ironmate_venv')  # Exclude .ironmate_venv directories
        for filename in filenames:
            if any(filename.endswith(ext) for ext in _DEFAULT_EXTENSIONS):
                found_files.append(os.path.join(dirpath, filename))
    return found_files

# Function to find files and return their paths as a map

def find_files_as_map(root_directory):
    file_map = {}
    for dirpath, dirnames, filenames in os.walk(root_directory):
        if '__pycache__' in dirnames:
            dirnames.remove('__pycache__')  # Exclude __pycache__ directories
        if '.ironmate_venv' in dirnames:
            dirnames.remove('.ironmate_venv')  # Exclude .ironmate_venv directories
        for filename in filenames:
            if any(filename.endswith(ext) for ext in _DEFAULT_EXTENSIONS):
                file_map[filename] = os.path.join(dirpath, filename)
    return file_map
