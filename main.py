import sys
import time

from PyQt5 import QtWidgets, uic
import serial
import ecg_plot
import numpy as np
from tqdm import tqdm
import csv

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


def adcvoltage(rawdata, adcmax=0x800000):
    try:
        rawdata = (float(rawdata) / adcmax)
    except:
        return 0
    rawdata = rawdata - (1 / 2)
    rawdata = rawdata * 4.8
    rawdata = rawdata / 3.5
    return rawdata


def ecg_read(ADCMax, bandwidth, DATA_LIM=500):
    stop = 0
    index = 0
    x_vals = range(DATA_LIM)
    y_vals = np.empty([6, DATA_LIM])
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
                data[0] = adcvoltage(data[0], ADCMax)
                data[1] = adcvoltage(data[1], ADCMax)
                data[2] = adcvoltage(data[2], ADCMax)
                # print("Lead 1: %s, Lead 2: %s, Lead 3: %s" % (data[0], data[1], data[2]))
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
    ecg_plot.plot(y_vals, sample_rate=bandwidth, title='ECG 6 Lead', columns=2)
    ecg_plot.show()
    return 0


def valLookup(bw):
    # TODO: Make sure that bandwidth values do not occur twice, and if so chose one with lower noise or first one if same
    with open('sampling.csv', newline='') as parameters:
        read = csv.reader(parameters, delimiter=',', quotechar='"')
        x = 0
        for row in read:
            if x == 0:
                x = 1
                continue
            if row[4] == bw:
                return row[0], row[1], row[2], row[3], row[6]
            x += 1


class MyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()
        uic.loadUi("mainwindow.ui", self)

        self.noiseline.setReadOnly(True)
        self.ODRline.setReadOnly(True)

        self.populatecombo()

        self.startButton.clicked.connect(self.startclick)
        self.paramButton.clicked.connect(self.setparam)
        self.stopButton.clicked.connect(self.stop)

        self.bandwidth = 0
        self.time = 0
        self.points = 0

        self.ADCMax = 0
        self.ODR = 0
        self.noise = 0

        self.R2 = 0x01
        self.R3 = 0x02

    def populatecombo(self):
        with open('sampling.csv', newline='') as parameters:
            read = csv.reader(parameters, delimiter=',', quotechar='"')
            x = 0
            for row in read:
                if x == 0:
                    x = 1
                    continue
                self.samplingrline.addItem(row[4] + " Hz", row[4])

    def setparam(self):
        self.time = self.samplingline.text()
        self.bandwidth = self.samplingrline.currentData()
        self.points = int(self.time) * int(self.bandwidth)
        self.R2, self.R3, self.ADCMax, self.ODR, self.noise = valLookup(self.bandwidth)
        self.R2 = R2_to_Hex(float(self.R2))
        self.R3 = R3_to_Hex(float(self.R3))
        self.noiseline.setText("%s uV" % self.noise)
        self.ODRline.setText("%s Hz" % self.ODR)

    def stop(self):
        sendData(CONFIG_Reg, bin_to_hex('00000000'))

    def startclick(self):
        print("ECG Measurement Init")
        global bool1
        bool1 = not bool1
        self.upload()
        ecg_read(self.ADCMax, int(self.bandwidth), int(self.points))

    def upload(self):
        print("Uploading decimation rates R2: %s R3: %s" % (self.R2, self.R3))
        sendData(R2_Reg, self.R2)
        sendData(R3CH1_Reg, self.R3)
        sendData(R3CH2_Reg, self.R3)
        sendData(R3CH3_Reg, self.R3)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MyWindow()
    window.show()
    sys.exit(app.exec())
