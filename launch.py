"""Run from a source checkout or a portable distribution."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent/'_vendor'))
from photosort.cli import main
main(sys.argv[1:] or ['gui'])
