"""
This is a program which acts as a controller and interpreter for my ultra-low-cost ECG Systolic.
"""
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

from configparser import ConfigParser, NoOptionError, NoSectionError

from scipy import signal
from scipy.signal import butter

from mathtools import mean_downscaler

# These are the two files for if the ADS1293's SDM is running at 204.8 kHz or at 102.4 kHz
# CSV_FILE = 'csv/sampling_1024.csv' # 102.4 kHz
CSV_FILE = 'csv/sampling_2048.csv'  # 204.8 kHz

CONFIG_REG = "0x00"
R2_REG = "0x21"
R3CH1_REG = "0x22"
R3CH2_REG = "0x23"
R3CH3_REG = "0x24"
CM_REG = '0x0B'
RLD_REG = '0x0C'
AFE_REG = '0x13'
FILTER_REG = '0x26'


def __butter_filter(order, crit_freq, filter_type, sampling_freq, data):
    sos = butter(order, crit_freq, btype=filter_type, output='sos', fs=sampling_freq)
    fData = signal.sosfilt(sos, data)
    # return filteredData
    return fData


def pan_tompkins(waveform, fs, order=2):
    """
    :param waveform: Waveform data, Lead II is used
    :type waveform: ndarray
    :param fs: Sampling Frequency (Hz)
    :type fs: float
    :param order: Order of notch filter applied from 5-15 Hz
    :type order: int
    :return: Heart rate
    :rtype: int
    """
    # Use Lead II
    waveform = waveform[1]
    # Calculate sampling time
    sampleTime = len(waveform) / fs
    # Firstly 5-15 Hz bandpass is applied
    low = 5
    high = 15
    waveformFilt = __butter_filter(order, [low, high], 'bandpass', fs, waveform)
    # Derivative filter
    waveformFilt = np.gradient(waveformFilt)
    # Square signal
    waveformFilt = waveformFilt ** 2
    # Calculate moving average
    averageWindow = 0.15  # seconds
    sampleAmount = int(averageWindow * fs)
    waveformFilt = mean_downscaler(waveformFilt, sampleAmount)
    """If point in moving average is greater than 0.4, then it is a beat. Wait refractory period (well approximately 
    in this case) Right now I've gone the lazy way of just using a constant value to count as a beat, but in future I 
    will do it properly like discussed in the  article I linked before. """
    beats = 0
    refractory = 0
    xPoints = []
    yPoints = []
    for i, x in enumerate(waveformFilt):
        if (i + 1) >= len(waveformFilt):
            break
        if x > 0 and waveformFilt[i + 1] <= x and x > 0.002:
            beats += 1
            refractory = i
        # I can't exactly wait 200 ms, so I have to just skip 1
        if i == (refractory + 1):
            continue
    hRate = round(beats / sampleTime * 60)
    # return hRate
    return hRate


def saveData(name, headers, data, samplingRate):
    if data is None:
        return
    with open(name, 'wt', newline='') as csvObject:
        csv_writer = csv.writer(csvObject, delimiter=',')
        # Settings header
        settings = ['samplingRate', samplingRate]
        # Data headers
        csv_writer.writerow(settings)
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


def bin_to_hex(binaryIn):
    hexb = hex(int(binaryIn, 2))[2:]
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


def adcVoltage(rawdata, adcmax=0x800000):
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
    sendData(CONFIG_REG, bin_to_hex('00000001'), ser)
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
                data[0] = adcVoltage(data[0], ADCMax)
                data[1] = adcVoltage(data[1], ADCMax)
                data[2] = adcVoltage(data[2], ADCMax)
                # print("Lead 1: %s, Lead 2: %s, Lead 3: %s" % (data[0], data[1], data[2]))
                y_vals[0][i] = data[0]
                y_vals[1][i] = data[1]
                y_vals[2][i] = data[2]
                # time.sleep(1/500)
                break
    end = time.time()
    pointNum = len(y_vals[0])
    delta = end - start
    sRate = pointNum / delta
    print("Sampling Rate: %s" % sRate)
    sendData(CONFIG_REG, bin_to_hex('00000000'), ser)
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
    samp_freq = sRate

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
    with open(CSV_FILE, newline='') as parameters:
        read = csv.reader(parameters, delimiter=',', quotechar='"')
        x = 0
        for row in read:
            if x == 0:
                x = 1
                continue
            if row[4] == bw:
                return row[0], row[1], row[2], row[3], row[6]
            x += 1


class _ECGWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(_ECGWindow, self).__init__()
        uic.loadUi("mainwindow.ui", self)

        self.noiseline.setReadOnly(True)
        self.ODRline.setReadOnly(True)
        self.statusLine.setReadOnly(True)
        self.heartrateLine.setReadOnly(True)
        self.viewButton.setEnabled(False)
        self.saveButton.setEnabled(False)
        self.analysisButton.setEnabled(False)

        self.statusLine.setText("Disconnected")

        self.startButton.clicked.connect(self.start_sampling)
        self.paramButton.clicked.connect(self.set_param)
        self.refreshButton.clicked.connect(self.refresh_COM)
        self.conButton.clicked.connect(self.connect)
        self.stopButton.clicked.connect(self.stop)
        self.saveButton.clicked.connect(lambda: saveData('sample.csv', self.headers, self.waveforms, self.samplingRate))
        self.viewButton.clicked.connect(lambda: viewData(self.waveforms, self.samplingRate))
        self.loadButton.clicked.connect(self.load_data)
        self.analysisButton.clicked.connect(self.analysis)
        self.samplingline.textChanged.connect(self.update_var)
        self.samplingrline.currentTextChanged.connect(self.update_var)

        self.conn_state(0)

        # USED TO DETERMINE UNSAVED CHANGES
        self.updated = 0

        # CONNECTION PARAMETERS
        self.port = 0
        self.baud = 115200
        self.ser = None
        self.connected = 0

        # ECG READ DATA & FUNCTIONS
        self.waveforms = []
        self.samplingRate = 0
        self.heartRate = 0
        self.headers = ['Lead I', 'Lead II', 'Lead III', 'aVR', 'aVL', 'aVF']

        # SAMPLING PARAMETERS - USER SET. BELOW ARE THE DEFAULTS
        self.bandwidth = 160
        self.time = "5"

        # ADJUSTED BASED ON BANDWIDTH AND TIME SETTINGS
        self.R2 = 0x01
        self.R3 = 0x02
        self.points = 300
        self.ADCMax = "0x800000"
        self.ODR = 0
        self.noise = 0
        self.odrArr = []

        # MISCELLANEOUS PARAMETERS
        self.configName = 'config.ini'

        # SETS TAB TO CONNECTION PAGE, FOR IF THE UI FILE IS SAVED AS TO HAVE ANOTHER TAB AS DEFAULT
        self.Tabs.setCurrentIndex(2)

        # FINAL FUNCTIONS TO SETUP WINDOW
        self.populate_band()
        self.refresh_COM()
        self.config = ConfigParser()
        self.load_config()

    def analysis(self):
        """
        Wrapper for analysis functions, only contains heart rate calculation currently.
        """
        self.heartRate = pan_tompkins(self.waveforms, self.samplingRate)
        self.heartrateLine.setText("%s bpm" % self.heartRate)

    def load_data(self):
        # Temporary filepath for my testing
        path = 'cardiacwaveforms.csv'
        with open(path, newline='') as csvfile:
            dataReader = csv.reader(csvfile, delimiter=',', quotechar='|')
            for i, row in enumerate(dataReader):
                if i == 0:
                    # Sampling settings
                    self.samplingRate = float(row[1])
                    continue
                if i == 1:
                    # Headers
                    continue
                row = list(map(float, row))
                self.waveforms.append(row)
        self.waveforms = np.array(self.waveforms)
        # Transpose array as CSV data isn't in the preferred format
        self.waveforms = self.waveforms.T
        print("Data read")
        self.viewButton.setEnabled(True)
        self.analysisButton.setEnabled(True)

    def init_config(self):
        open(self.configName, 'w').close()
        self.config = ConfigParser()
        self.config.read(self.configName)
        self.config.add_section('main')
        self.config.set('main', 'bandwidth', str(self.bandwidth))
        self.config.set('main', 'time', str(self.time))
        with open('config.ini', 'w') as f:
            self.config.write(f)

    def load_config(self):
        data = self.config.read(self.configName)
        if len(data) == 0:
            self.init_config()
        else:
            try:
                self.bandwidth = self.config.get('main', 'bandwidth')
                self.time = self.config.get('main', 'time')
            except NoSectionError:
                self.init_config()
            except NoOptionError:
                self.init_config()
            finally:
                self.samplingline.clear()
                self.samplingline.insert(self.time)
                index = np.where(np.array(self.odrArr) == self.bandwidth)
                self.samplingrline.setCurrentIndex(int(index[0]))
                self.set_param()

    def conn_state(self, num):
        if num == 0:
            self.statusLine.setText("Disconnected")
        else:
            self.statusLine.setText("Connected")
        self.Tabs.setTabEnabled(1, num)
        self.connected = num

    def connect(self):
        self.port = self.comSel.currentData()
        if self.port is None or self.port == 0:
            return
        if self.connected == 1:
            try:
                self.ser.close()
                self.conn_state(0)
                return
            except serial.SerialException as e:
                print(e)
                self.conn_state(0)
        try:
            self.ser = serial.Serial(str(self.port), self.baud)  # open serial port
            self.conn_state(1)

        except serial.SerialException as e:
            error = QMessageBox()
            error.setIcon(QMessageBox.Warning)
            error.setText("An error occurred when trying to connect.")
            error.setWindowTitle("Systolic")
            error.setDetailedText(f"{e}")
            error.exec_()
            self.conn_state(0)
            return

    def refresh_COM(self):
        self.comSel.clear()
        availPorts = serial.tools.list_ports.comports()
        for port, desc, _ in sorted(availPorts):
            self.comSel.addItem(desc, port)

    def update_var(self):
        self.updated = 1

    def populate_band(self):
        with open(CSV_FILE, newline='') as parameters:
            read = csv.reader(parameters, delimiter=',', quotechar='"')
            start = False
            last = 0
            for row in read:
                if not start:
                    start = True
                    continue
                if row[4] == last:
                    continue
                last = row[4]
                self.odrArr.append(row[4])
                self.samplingrline.addItem(row[4] + " Hz", row[4])

    def set_param(self):
        self.updated = 0
        self.time = self.samplingline.text()
        self.bandwidth = self.samplingrline.currentData()
        self.R2, self.R3, self.ADCMax, self.ODR, self.noise = valLookup(self.bandwidth)
        self.points = int(self.time) * int(self.ODR)
        self.R2 = R2_to_Hex(float(self.R2))
        self.R3 = R3_to_Hex(float(self.R3))

        self.noiseline.setText("%s uV" % self.noise)
        self.ODRline.setText("%s Hz" % self.ODR)

        self.config.set('main', 'bandwidth', str(self.bandwidth))
        self.config.set('main', 'time', str(self.time))
        with open(self.configName, 'w') as f:
            self.config.write(f)

    def stop(self):
        sendData(CONFIG_REG, bin_to_hex('00000000'), self.ser)

    def start_sampling(self):
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
        self.analysisButton.setEnabled(True)
        viewData(self.waveforms, self.samplingRate)
        # Move user to sample tab
        self.Tabs.setCurrentIndex(0)
        self.analysis()

    def upload(self):
        print("Uploading decimation rates R2: %s R3: %s" % (self.R2, self.R3))
        sendData(R2_REG, self.R2, self.ser)
        sendData(R3CH1_REG, self.R3, self.ser)
        sendData(R3CH2_REG, self.R3, self.ser)
        sendData(R3CH3_REG, self.R3, self.ser)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = _ECGWindow()
    window.show()
    sys.exit(app.exec())
