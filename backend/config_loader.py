import os
import sys
import importlib.util

# Default configuration path
EXAMPLE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.example.py")
LOCAL_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")

# Try to load local config, otherwise fallback to example config
config_path = LOCAL_CONFIG_PATH if os.path.exists(LOCAL_CONFIG_PATH) else EXAMPLE_CONFIG_PATH

spec = importlib.util.spec_from_file_location("dynamic_config", config_path)
dynamic_config = importlib.util.module_from_spec(spec)
sys.modules["dynamic_config"] = dynamic_config
spec.loader.exec_module(dynamic_config)

# Export all upper-case variables from the loaded config
for key in dir(dynamic_config):
    if key.isupper():
        globals()[key] = getattr(dynamic_config, key)
