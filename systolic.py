import sys
import time

from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QMessageBox

import serial
import serial.tools.list_ports

import ecg_plot
import numpy as np
from tqdm import tqdm
import csv

import matplotlib.pyplot as plt
from scipy import signal

# These are the two files for if the ADS1293's SDM is running at 204.8 KHz or at 102.4 KHz
# csv_file = 'csv/sampling_1024.csv'
csv_file = 'csv/sampling_2048.csv'

CONFIG_Reg = "0x00"
R2_Reg = "0x21"
R3CH1_Reg = "0x22"
R3CH2_Reg = "0x23"
R3CH3_Reg = "0x24"
CM_Reg = '0x0B'
RLD_Reg = '0x0C'
AFE_Reg = '0x13'
Filter_Reg = '0x26'


def saveData(name, headers, data):
    if data is None:
        return
    with open(name, 'wt', newline='') as csvObject:
        csv_writer = csv.writer(csvObject, delimiter=',')
        csv_writer.writerow(headers)  # write header
        colsIndices = np.arange(len(data[0]))
        rowsIndices = np.arange(len(data))
        rowData = []
        """
        I know this is overcomplicating a simple task of iterating over 6 rows, however I wanted to do it this way
        just incase in future I wanted to call this function with just three rows of data. It wouldn't be fun if
        the function didn't work then!
        """
        for columnIndex in colsIndices:
            for rowIndex in rowsIndices:
                rowData.append(data[rowIndex][columnIndex])
            csv_writer.writerow(rowData)
            rowData = []


def bin_to_hex(binaryin):
    hexb = hex(int(binaryin, 2))[2:]
    hexb = hexb.zfill(2)
    hexb = "0x" + hexb
    return hexb


def R2_to_Hex(x):
    if x == 4:
        return bin_to_hex('00000001')
    if x == 5:
        return bin_to_hex('00000010')
    if x == 6:
        return bin_to_hex('00000100')
    if x == 8:
        return bin_to_hex('00001000')


def R3_to_Hex(x):
    if x == 4:
        return bin_to_hex('00000001')
    if x == 6:
        return bin_to_hex('00000010')
    if x == 8:
        return bin_to_hex('00000100')
    if x == 12:
        return bin_to_hex('00001000')
    if x == 16:
        return bin_to_hex('00010000')
    if x == 32:
        return bin_to_hex('00100000')
    if x == 64:
        return bin_to_hex('01000000')
    if x == 128:
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


def sendData(register, rawData, ser):
    rawData = str(rawData)
    register = str(register)
    rawData = register + "," + rawData
    data = rawData + "\r\n"
    try:
        ser.write(data.encode())
        print("Sent: %s" % rawData)
    except Exception as e:
        print("Serial port write failed \n")
        print("Flag: %s \n" % e)


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


def ecg_read(ADCMax, ser, DATA_LIM=500):
    # DATA_LIM = 160 * 5
    DATA_LIM = round(DATA_LIM)
    stop = 0
    y_vals = np.empty([6, DATA_LIM])
    sendData(CONFIG_Reg, bin_to_hex('00000001'), ser)
    time.sleep(1)
    ser.reset_input_buffer()
    start = time.time()
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
                # time.sleep(1/500)
                break
    end = time.time()
    xtick = 0
    for i in y_vals[0]:
        xtick += 1
    delta = end - start
    srate = xtick / delta
    print("Sampling Rate: %s" % srate)
    sendData(CONFIG_Reg, bin_to_hex('00000000'), ser)
    index = 0
    average_i = np.average(y_vals[0])
    average_ii = np.average(y_vals[1])
    average_iii = np.average(y_vals[2])
    for i in range(0, DATA_LIM):
        y_vals[0][i] = (y_vals[0][i] - average_i) * pow(10, 3)
        y_vals[1][i] = (y_vals[1][i] - average_ii) * pow(10, 3)
        y_vals[2][i] = (y_vals[2][i] - average_iii) * pow(10, 3)
        y_vals[3][i] = -1 * (float(y_vals[0][i]) + float(y_vals[1][i])) / 2  # aVR
        y_vals[4][i] = (float(y_vals[0][i]) - float(y_vals[1][i])) / 2  # aVL
        y_vals[5][i] = (float(y_vals[1][i]) - float(y_vals[0][i])) / 2  # aVF
    average_aVR = np.average(y_vals[3])
    average_aVL = np.average(y_vals[4])
    average_aVF = np.average(y_vals[5])
    for i in range(0, DATA_LIM):
        y_vals[3][i] = y_vals[3][i] - average_aVR
        y_vals[4][i] = y_vals[4][i] - average_aVL
        y_vals[5][i] = y_vals[5][i] - average_aVF

    # Sample frequency (Hz)
    samp_freq = srate

    # Frequency to be removed from signal (Hz)
    notch_freq = 50.0  # For usage in areas with 50 Hz mains power
    # notch_freq = 60.0 # For usage in areas with 60 Hz mains power

    # Quality factor
    quality_factor = 30.0

    b_notch, a_notch = signal.iirnotch(notch_freq, quality_factor, samp_freq)

    # 50 Hz notch filter applied to all 6 leads
    y_vals[0] = signal.filtfilt(b_notch, a_notch, y_vals[0])
    y_vals[1] = signal.filtfilt(b_notch, a_notch, y_vals[1])
    y_vals[2] = signal.filtfilt(b_notch, a_notch, y_vals[2])
    y_vals[3] = signal.filtfilt(b_notch, a_notch, y_vals[3])
    y_vals[4] = signal.filtfilt(b_notch, a_notch, y_vals[4])
    y_vals[5] = signal.filtfilt(b_notch, a_notch, y_vals[5])

    return y_vals, samp_freq


def viewData(waveforms, samplingRate, title='ECG 6 Lead'):
    ecg_plot.plot(waveforms, sample_rate=samplingRate, title=title, columns=2)
    ecg_plot.show()


def valLookup(bw):
    with open(csv_file, newline='') as parameters:
        read = csv.reader(parameters, delimiter=',', quotechar='"')
        x = 0
        for row in read:
            if x == 0:
                x = 1
                continue
            if row[4] == bw:
                return row[0], row[1], row[2], row[3], row[6]
            x += 1


# TODO: Add Waveform loading
# TODO: Add sampling information into saved file (Sampling time, Bandwidth, etc.)

class MyWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()
        uic.loadUi("mainwindow.ui", self)

        self.samplingline.setText("5")
        self.noiseline.setReadOnly(True)
        self.ODRline.setReadOnly(True)
        self.statusLine.setReadOnly(True)
        self.viewButton.setEnabled(False)
        self.saveButton.setEnabled(False)

        self.statusLine.setText("Disconnected")

        self.populateband()
        self.refreshCOM()

        self.startButton.clicked.connect(self.startclick)
        self.paramButton.clicked.connect(self.setparam)
        self.refreshButton.clicked.connect(self.refreshCOM)
        self.conButton.clicked.connect(self.connect)
        self.stopButton.clicked.connect(self.stop)

        self.connstate(0)

        self.samplingline.textChanged.connect(self.updatevar)
        self.samplingrline.currentTextChanged.connect(self.updatevar)

        # USED TO DETERMINE UNSAVED CHANGES
        self.updated = 0

        # CONNECTION PARAMETERS
        self.port = 0
        self.baud = 115200
        self.ser = None
        self.connected = 0

        # ECG READ DATA & FUNCTIONS
        self.waveforms = None
        self.samplingRate = 0
        self.headers = ['Lead I', 'Lead II', 'Lead III', 'aVR', 'aVL', 'aVF']
        self.saveButton.clicked.connect(lambda: saveData('sample.csv', self.headers, self.waveforms))
        self.viewButton.clicked.connect(lambda: viewData(self.waveforms, self.samplingRate))

        # USER SET IN SETTINGS
        self.bandwidth = 160
        self.time = "5"

        # ADUSTED BASED ON BANDWIDTH AND TIME SETTINGS
        self.R2 = 0x01
        self.R3 = 0x02
        self.points = 300
        self.ADCMax = "0x800000"
        self.ODR = 0
        self.noise = 0

    def connstate(self, num):
        if num == 0:
            self.statusLine.setText("Disconnected")
        else:
            self.statusLine.setText("Connected")
        self.Tabs.setTabEnabled(0, num)
        self.connected = num

    def connect(self):
        self.port = self.comSel.currentData()
        if self.port is None or self.port == 0:
            return
        if self.connected == 1:
            try:
                self.ser.close()
                self.connstate(0)
                return
            except serial.SerialException as e:
                self.connstate(0)
        try:
            self.ser = serial.Serial(str(self.port), self.baud)  # open serial port
            self.connstate(1)

        except serial.SerialException as e:
            error = QMessageBox()
            error.setIcon(QMessageBox.Warning)
            error.setText("An error occurred when trying to connect.")
            error.setWindowTitle("Systolic")
            error.setDetailedText(f"{e}")
            error.exec_()
            self.connstate(0)
            return

    def refreshCOM(self):
        self.comSel.clear()
        availPorts = serial.tools.list_ports.comports()
        for port, desc, hwid in sorted(availPorts):
            self.comSel.addItem(desc, port)

    def updatevar(self):
        self.updated = 1

    def populateband(self):
        with open(csv_file, newline='') as parameters:
            read = csv.reader(parameters, delimiter=',', quotechar='"')
            x = 0
            last = 0
            for row in read:
                if x == 0:
                    x = 1
                    continue
                if row[4] == last:
                    continue
                last = row[4]
                self.samplingrline.addItem(row[4] + " Hz", row[4])

    def setparam(self):
        self.updated = 0
        self.time = self.samplingline.text()
        self.bandwidth = self.samplingrline.currentData()
        self.R2, self.R3, self.ADCMax, self.ODR, self.noise = valLookup(self.bandwidth)
        self.points = int(self.time) * int(self.ODR)
        self.R2 = R2_to_Hex(float(self.R2))
        self.R3 = R3_to_Hex(float(self.R3))
        self.noiseline.setText("%s uV" % self.noise)
        self.ODRline.setText("%s Hz" % self.ODR)

    def stop(self):
        sendData(CONFIG_Reg, bin_to_hex('00000000'), self.ser)

    def startclick(self):
        print(self.updated)
        if self.updated == 1:
            ret = QMessageBox.question(self, 'Warning',
                                       "You have modified your sampling parameters but have not set them. Continue?",
                                       QMessageBox.Yes | QMessageBox.No)
            if ret == QMessageBox.No:
                return
        print("ECG Measurement Init")
        self.upload()
        self.waveforms, self.samplingRate = ecg_read(int(self.ADCMax, 16), self.ser, int(self.points))

        self.viewButton.setEnabled(True)
        self.saveButton.setEnabled(True)

        viewData(self.waveforms, self.samplingRate)

    def upload(self):
        print("Uploading decimation rates R2: %s R3: %s" % (self.R2, self.R3))
        sendData(R2_Reg, self.R2, self.ser)
        sendData(R3CH1_Reg, self.R3, self.ser)
        sendData(R3CH2_Reg, self.R3, self.ser)
        sendData(R3CH3_Reg, self.R3, self.ser)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MyWindow()
    window.show()
    sys.exit(app.exec())
