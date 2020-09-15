import sys
import time

from PyQt5 import QtWidgets, uic, QtCore
import serial
import ecg_plot
import numpy as np
from tqdm import tqdm

import random
from itertools import count

from matplotlib.animation import FuncAnimation

DATA_LIM = 500
x_vals = range(DATA_LIM)
y_vals = np.empty([6, DATA_LIM])
index = 0
"""plt.style.use('fivethirtyeight')
plt.tight_layout()
plt.ion()
plt.show()"""

bool1 = False

CONFIG_Reg = "0x00"
R2_Reg = "0x21"
R3CH1_Reg = "0x22"
R3CH2_Reg = "0x23"
R3CH3_Reg = "0x24"
CM_Reg = '0x0B'
RLD_Reg = '0x0C'
AFE_Reg = '0x13'
Filter_Reg = '0x26'

stop = 0


def bin_to_hex(bin):
    hexb = hex(int(bin, 2))[2:]
    hexb = hexb.zfill(2)
    hexb = "0x" + hexb
    return hexb


def R2_to_Hex(x):
    if x == 4:
        return bin_to_hex('00000001')
    elif x == 5:
        return bin_to_hex('00000010')
    elif x == 6:
        return bin_to_hex('00000100')
    elif x == 8:
        return bin_to_hex('00001000')


def R3_to_Hex(x):
    if x == 4:
        return bin_to_hex('00000001')
    elif x == 6:
        return bin_to_hex('00000010')
    elif x == 8:
        return bin_to_hex('00000100')
    elif x == 12:
        return bin_to_hex('00001000')
    elif x == 16:
        return bin_to_hex('00010000')
    elif x == 32:
        return bin_to_hex('00100000')
    elif x == 64:
        return bin_to_hex('01000000')
    elif x == 128:
        return bin_to_hex('10000000')


def CM_to_Hex(bandwidth, drive):
    binary = '00000'
    if bandwidth:
        binary = binary + '1'
    else:
        binary = binary + '0'
    if drive == 0:
        binary = binary + '00'
    elif drive == 1:
        binary = binary + '01'
    elif drive == 2:
        binary = binary + '10'
    elif drive == 3:
        binary = binary + '11'
    return bin_to_hex(binary)


def RLD_to_Hex(toggle, bandwidth, drive):
    binary = '0'
    if bandwidth:
        binary = binary + '1'
    else:
        binary = binary + '0'
    if drive == 0:
        binary = binary + '00'
    elif drive == 1:
        binary = binary + '01'
    elif drive == 2:
        binary = binary + '10'
    elif drive == 3:
        binary = binary + '11'
    if toggle:
        # Not shutdown
        binary = binary + '0'
    else:
        # Shutdown
        binary = binary + '1'
    # Default to IN4
    binary = binary + '100'
    return bin_to_hex(binary)


def AFE_to_Hex(C1, C2, C3):
    binary = '00'
    # Default Clock
    binary = binary + '000'
    if C1:
        binary = binary + '1'
    else:
        binary = binary + '0'
    if C2:
        binary = binary + '1'
    else:
        binary = binary + '0'
    if C3:
        binary = binary + '1'
    else:
        binary = binary + '0'
    return bin_to_hex(binary)


def Filter_to_Hex(C1, C2, C3):
    binary = '00000'
    if C3:
        binary = binary + '0'
    else:
        binary = binary + '1'
    if C2:
        binary = binary + '0'
    else:
        binary = binary + '1'
    if C1:
        binary = binary + '0'
    else:
        binary = binary + '1'
    return bin_to_hex(binary)


def sendData(register, data):
    try:
        ser = serial.Serial('COM16', 115200)  # open serial port
    except Exception as e:
        print("Serial port opening for tx failed \n")
        print("Flag: %s \n" % e)
    data = str(data)
    register = str(register)
    data = register + "," + data
    data += "\r\n"
    try:
        ser.write(data.encode())
        print("Sent: %s" % data)
    except Exception as e:
        print("Serial port write failed \n")
        print("Flag: %s \n" % e)
    ser.close()


def hasNumbers(inputString):
    return any(char.isdigit() for char in inputString)


def adcvoltage(rawdata):
    try:
        rawdata = (float(rawdata) / 0x800000)
    except:
        return 0
    rawdata = rawdata - (1 / 2)
    rawdata = rawdata * 4.8
    rawdata = rawdata / 3.5
    return rawdata


def ecg_read():
    global y_vals
    global stop
    global index
    sendData(CONFIG_Reg, bin_to_hex('00000001'))
    time.sleep(1)

    try:
        ser = serial.Serial('COM16', 115200)  # open serial port
    except Exception as e:
        print("Serial port opening for ecg read failed \n")
        print("Flag: %s \n" % e)
    ser.flush()
    for i in tqdm(range(0, DATA_LIM)):
        while not stop:
            bytesToRead = ser.inWaiting()
            data = ser.read(bytesToRead)
            data = data.decode('utf-8')
            data = data.strip()
            if hasNumbers(data):
                try:
                    data = data.split(",")
                except:
                    break
                # y_vals[index] = data[0]
                data[0] = adcvoltage(data[0])
                data[1] = adcvoltage(data[1])
                data[2] = adcvoltage(data[2])
                # print("Lead 1: %s, Lead 2: %s, Lead 3: %s" % (data[0], data[1], data[2]))
                # data = data - 649
                y_vals[0][i] = data[0]
                y_vals[1][i] = data[1]
                y_vals[2][i] = data[2]
                break
    ser.close()
    sendData(CONFIG_Reg, bin_to_hex('00000000'))
    index = 0
    average_i = np.average(y_vals[0])
    average_ii = np.average(y_vals[1])
    average_iii = np.average(y_vals[2])
    for i in range(0, DATA_LIM):
        y_vals[0][i] = y_vals[0][i] - average_i
        y_vals[1][i] = y_vals[1][i] - average_ii
        y_vals[2][i] = y_vals[2][i] - average_iii
        y_vals[3][i] = -1 * (float(y_vals[0][i]) + float(y_vals[1][i])) / 2  # aVR
        y_vals[4][i] = (float(y_vals[0][i]) - float(y_vals[1][i])) / -2  # aVL
        y_vals[5][i] = (float(y_vals[1][i]) - float(y_vals[0][i])) / -2  # aVF
    average_aVR = np.average(y_vals[3])
    average_aVL = np.average(y_vals[4])
    average_aVF = np.average(y_vals[5])
    for i in range(0, DATA_LIM):
        y_vals[3][i] = y_vals[3][i] - average_aVR
        y_vals[4][i] = y_vals[4][i] - average_aVL
        y_vals[5][i] = y_vals[5][i] - average_aVF
    ecg_plot.plot(y_vals, sample_rate=150, title='ECG 6 Lead', columns=2)
    ecg_plot.show()
    return 0


"""try:
    thread = threading.Thread(target=ecg_read, args=(ser,))
    thread.start()
except (KeyboardInterrupt, SystemExit):
    ser.close()
    sys.exit()
"""


class MyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()
        uic.loadUi("mainwindow.ui", self)
        self.startButton.clicked.connect(self.startclick)
        self.uploadButton.clicked.connect(self.upload)
        self.stopButton.clicked.connect(self.stop)

    def stop(self):
        sendData(CONFIG_Reg, bin_to_hex('00000000'))

    def startclick(self):
        print("Start clicked")
        global bool1
        self.tabWidget.setTabEnabled(1, False)
        bool1 = not bool1
        ecg_read()
        self.tabWidget.setTabEnabled(1, True)

    def upload(self):
        self.progressBar.setValue(0)

        CMBand = self.CMBW.isChecked()
        CMDrive = self.CMDrv.currentIndex()
        CM = CM_to_Hex(CMBand, CMDrive)

        RLDToggle = self.RLDToggle.isChecked()
        RLDBand = self.RLDBW.isChecked()
        RLDDrive = self.RLDDrv.currentIndex()
        RLD = RLD_to_Hex(RLDToggle, RLDBand, RLDDrive)

        AFECH1 = self.C1Res.isChecked()
        AFECH2 = self.C2Res.isChecked()
        AFECH3 = self.C3Res.isChecked()
        AFE = AFE_to_Hex(AFECH1, AFECH2, AFECH3)

        FiltC1 = self.C1Filter.isChecked()
        FiltC2 = self.C2Filter.isChecked()
        FiltC3 = self.C3Filter.isChecked()
        Filt = Filter_to_Hex(FiltC1, FiltC2, FiltC3)

        R2 = R2_to_Hex(float(self.R2R.currentText()))
        R3 = R3_to_Hex(float(self.R3R.currentText()))

        print("Uploading!")

        progress = 100 / 8

        sendData(R2_Reg, R2)
        self.progressBar.setValue(int(progress * 1))
        sendData(R3CH1_Reg, R3)
        self.progressBar.setValue(int(progress * 2))
        sendData(R3CH2_Reg, R3)
        self.progressBar.setValue(int(progress * 3))
        sendData(R3CH3_Reg, R3)
        self.progressBar.setValue(int(progress * 4))
        sendData(CM_Reg, CM)
        self.progressBar.setValue(int(progress * 5))
        sendData(AFE_Reg, AFE)
        self.progressBar.setValue(int(progress * 6))
        sendData(RLD_Reg, RLD)
        self.progressBar.setValue(int(progress * 7))
        sendData(Filter_Reg, Filt)
        self.progressBar.setValue(int(progress * 8))


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MyWindow()
    window.show()
    sys.exit(app.exec())

"""
app = QtWidgets.QApplication(sys.argv)

window = uic.loadUi("mainwindow.ui")
window.pushButton.clicked.connect(convert)
window.radioButton.clicked.connect(disable)
window.show()
app.exec()
"""