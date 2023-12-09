import sys

from PyQt5.QtWidgets import QApplication
from multiremodnav.MultiRemodnavWindow import MultiRemodnavWindow

def main():
    app = QApplication(sys.argv)
    ex = MultiRemodnavWindow()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
