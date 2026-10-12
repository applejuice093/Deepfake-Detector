import os
import sys

# Make `import main` work and resolve relative dirs (uploads/, frontend/).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
