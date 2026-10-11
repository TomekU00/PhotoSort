import sys
from photosort.cli import main
if __name__ == '__main__':
    main(sys.argv[1:] or ['--help'])
