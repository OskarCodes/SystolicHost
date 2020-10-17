"""
This is a program which acts as a controller and interpreter for my ultra-low-cost ECG Systolic.
"""
import sys
import time

import csv
from configparser import ConfigParser, NoOptionError, NoSectionError

from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QMessageBox

import serial
import serial.tools.list_ports

import ecg_plot
import numpy as np
from tqdm import tqdm

from scipy import signal

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


def __butter_filter(order, critical_freq, filter_type, sampling_freq, data):
    """
    Butter filter with adjustable type, etc.
    :param order: Filter order
    :type order: int
    :param critical_freq: Critical frequencies (-3 dB points)
    :type critical_freq: scalar or sequence (len 2)
    :param filter_type: Type of filter, e.g. 'lowpass', 'highpass', 'bandpass', etc.
    :type filter_type: string
    :param sampling_freq: Sampling frequency
    :type sampling_freq: float
    :param data: Input data to be filtered
    :type data: array
    :return: Filtered data
    :rtype: array
    """
    sos = signal.butter(order, critical_freq, btype=filter_type, output='sos', fs=sampling_freq)
    f_data = signal.sosfilt(sos, data)
    # return filtered data
    return f_data


def pan_tompkins(waveform, sampling_freq, order=2):
    """
    :param waveform: Waveform data, Lead II is used
    :type waveform: ndarray
    :param sampling_freq: Sampling Frequency (Hz)
    :type sampling_freq: float
    :param order: Order of notch filter applied from 5-15 Hz
    :type order: int
    :return: Heart rate
    :rtype: int
    """
    # Use Lead II
    waveform = waveform[1]
    # Calculate sampling time
    sample_time = len(waveform) / sampling_freq
    # Firstly 5-15 Hz bandpass is applied
    low = 5
    high = 15
    waveform_filt = __butter_filter(order, [low, high], 'bandpass', sampling_freq, waveform)
    # Derivative filter
    waveform_filt = np.gradient(waveform_filt)
    # Square signal
    waveform_filt = waveform_filt ** 2
    # Calculate moving average
    average_window = 0.15  # seconds
    sample_amount = int(average_window * sampling_freq)
    waveform_filt = mean_downscaler(waveform_filt, sample_amount)
    """If point in moving average is greater than 0.4, then it is a beat. Wait refractory period (well approximately 
    in this case) Right now I've gone the lazy way of just using a constant value to count as a beat, but in future I 
    will do it properly like discussed in the  article I linked before. """
    beats = 0
    refractory = 0
    for i, value in enumerate(waveform_filt):
        if (i + 1) >= len(waveform_filt):
            break
        if value > 0 and waveform_filt[i + 1] <= value and value > 0.002:
            beats += 1
            refractory = i
        # I can't exactly wait 200 ms, so I have to just skip 1
        if i == (refractory + 1):
            continue
    heart_rate = round(beats / sample_time * 60)
    # return heart_rate
    return heart_rate


def save_data(name, headers, data, sampling_rate):
    """
    Saves ECG data to csv
    :param name: File name for csv (include .csv)
    :type name: string
    :param headers: Headers for CSV (e.g. Lead I, Lead II, ...)
    :type headers: list
    :param data: ECG data
    :type data: array
    :param sampling_rate: Sampling rate
    :type sampling_rate: float
    """
    if data is None:
        return
    with open(name, 'wt', newline='') as csv_object:
        csv_writer = csv.writer(csv_object, delimiter=',')
        # Settings header
        settings = ['sampling_rate', sampling_rate]
        # Data headers
        csv_writer.writerow(settings)
        csv_writer.writerow(headers)  # write header
        cols_indices = np.arange(len(data[0]))
        rows_indices = np.arange(len(data))
        row_data = []
        """
        I know this is overcomplicating a simple task of iterating over 6 rows, however I wanted to do it this way
        just incase in future I wanted to call this function with just three rows of data. It wouldn't be fun if
        the function didn't work then!
        """
        for column_index in cols_indices:
            for row_index in rows_indices:
                row_data.append(data[row_index][column_index])
            csv_writer.writerow(row_data)
            row_data = []


def bin_to_hex(binary_in):
    """
    Converts a binary input to a hexadecimal output
    :param binary_in: Binary input
    :type binary_in: string
    :return: Hexadecimal output
    :rtype: int
    """
    hexb = hex(int(binary_in, 2))[2:]
    hexb = hexb.zfill(2)
    hexb = "0x" + hexb
    return hexb


def R2_to_Hex(R2_val):
    """
    R2 Decimation filter input integer to output hexadecimal
    """
    if R2_val == 4:
        return bin_to_hex('00000001')
    if R2_val == 5:
        return bin_to_hex('00000010')
    if R2_val == 6:
        return bin_to_hex('00000100')
    if R2_val == 8:
        return bin_to_hex('00001000')
    raise ValueError("Bad arguments")


def R3_to_Hex(R3_val):
    """
    R3 Decimation filter input integer to output hexadecimal
    """
    if R3_val == 4:
        return bin_to_hex('00000001')
    if R3_val == 6:
        return bin_to_hex('00000010')
    if R3_val == 8:
        return bin_to_hex('00000100')
    if R3_val == 12:
        return bin_to_hex('00001000')
    if R3_val == 16:
        return bin_to_hex('00010000')
    if R3_val == 32:
        return bin_to_hex('00100000')
    if R3_val == 64:
        return bin_to_hex('01000000')
    if R3_val == 128:
        return bin_to_hex('10000000')
    # Not good!
    raise ValueError("Bad arguments")


def CM_to_Hex(bandwidth, drive):
    """
    Common-mode (CM) drive input bool and integer to hexadecimal output
    """
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
    """
    Right-leg-drive (RLD) integer and bool inputs to hexadecimal output
    """
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
    """
    Analog-front-end (AFE) bool inputs to hexadecimal output
    """
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


def filter_to_hex(C1, C2, C3):
    """
    Digital filter binary inputs to hexadecimal output
    """
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


def send_data(register, raw_data, ser):
    """
    Sends data to ECG in format 'register,data'
    :param register: Register address
    :type register: int (Hex)
    :param raw_data: Data
    :type raw_data: int (Hex)
    :param ser: Serial object
    :type ser: serial
    """
    raw_data = str(raw_data)
    register = str(register)
    raw_data = register + "," + raw_data
    data = raw_data + "\r\n"
    try:
        ser.write(data.encode())
        print("Sent: %s" % raw_data)
    except Exception as what_went_wrong:
        print("Serial port write failed \n")
        print("Flag: %s \n" % what_went_wrong)


def has_numbers(input_string):
    """
    This function returns a boolean representing if the input string contains a number
    This is used in the ECG reading process
    :param input_string: The input string
    :type input_string: string
    :return: Boolean representing if input has numbers
    :rtype: bool
    """
    return any(char.isdigit() for char in input_string)


def adc_voltage(raw_data, adc_max=0x800000):
    """
    Function returns the analog voltage value converted from the digital received value
    :param raw_data: digital output
    :type raw_data: string
    :param adc_max: This value is from the lookup table
    :type adc_max: int
    :return:
    :rtype:
    """
    try:
        raw_data = (float(raw_data) / adc_max)
    except ValueError:
        # This often occurs with just the first piece of data.
        # No real way I can fix it right now.
        return 0
    raw_data -= (1 / 2)
    raw_data *= 4.8
    raw_data /= 3.5
    return raw_data


def ecg_read(adc_max, ser, data_limit):
    """
    Reads data from ECG
    :param adc_max: Value used to calculate voltage from adc output
    :type adc_max: int (Hex)
    :param ser: Serial object
    :type ser: serial
    :param data_limit: Amount of data to receive
    :type data_limit: integer
    """
    data_limit = round(data_limit)
    stop = 0
    y_vals = np.empty([6, data_limit])
    send_data(CONFIG_REG, bin_to_hex('00000001'), ser)
    # Need to consider if this sleep below is actually needed
    time.sleep(1)
    ser.reset_input_buffer()
    start = time.time()
    for i in tqdm(range(0, data_limit)):
        while not stop:
            data_to_read = ser.inWaiting()
            data = ser.read(data_to_read)
            data = data.decode('utf-8')
            data = data.strip()
            if has_numbers(data):
                try:
                    data = data.split(",")
                except Exception as what_went_wrong:
                    print(what_went_wrong)
                    break
                data[0] = adc_voltage(data[0], adc_max)
                data[1] = adc_voltage(data[1], adc_max)
                data[2] = adc_voltage(data[2], adc_max)
                y_vals[0][i] = data[0]
                y_vals[1][i] = data[1]
                y_vals[2][i] = data[2]
                break
    end = time.time()
    point_num = len(y_vals[0])
    delta_time = end - start
    sampling_rate = point_num / delta_time
    print(f"Time taken = {delta_time}")
    print(f"Time per sample = {delta_time/sampling_rate}")
    print(f"Sampling rate = {sampling_rate}")
    send_data(CONFIG_REG, bin_to_hex('00000000'), ser)
    average_i = np.average(y_vals[0])
    average_ii = np.average(y_vals[1])
    average_iii = np.average(y_vals[2])
    for i in range(0, data_limit):
        y_vals[0][i] = (y_vals[0][i] - average_i) * pow(10, 3)
        y_vals[1][i] = (y_vals[1][i] - average_ii) * pow(10, 3)
        y_vals[2][i] = (y_vals[2][i] - average_iii) * pow(10, 3)
        y_vals[3][i] = -1 * (float(y_vals[0][i]) + float(y_vals[1][i])) / 2  # aVR
        y_vals[4][i] = (float(y_vals[0][i]) - float(y_vals[1][i])) / 2  # aVL
        y_vals[5][i] = (float(y_vals[1][i]) - float(y_vals[0][i])) / 2  # aVF
    average_aVR = np.average(y_vals[3])
    average_aVL = np.average(y_vals[4])
    average_aVF = np.average(y_vals[5])
    for i in range(0, data_limit):
        y_vals[3][i] = y_vals[3][i] - average_aVR
        y_vals[4][i] = y_vals[4][i] - average_aVL
        y_vals[5][i] = y_vals[5][i] - average_aVF

    # Sample frequency (Hz)
    samp_freq = sampling_rate

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


def view_data(waveforms, sampling_rate, title='ECG 6 Lead'):
    """
    Displays ECG data using the awesome ecg-plot package
    :param waveforms: ECG Data
    :type waveforms: array
    :param sampling_rate: Sampling rate
    :type sampling_rate: float
    :param title: Title of plot
    :type title: string
    """
    ecg_plot.plot(waveforms, sample_rate=sampling_rate, title=title, columns=2)
    ecg_plot.show()


def value_lookup(bandwidth):
    """
    Looks for corresponding values in lookup table when given a bandwidth value
    :param bandwidth: Input val
    :type bandwidth: string
    :return: R2, R3, adc_max, ODR, noise
    :rtype: string, string, string, string, string
    """
    with open(CSV_FILE, newline='') as parameters:
        read = csv.reader(parameters, delimiter=',', quotechar='"')
        header = True
        for row in read:
            if header:
                header = False
                continue
            if row[4] == bandwidth:
                return row[0], row[1], row[2], row[3], row[6]
    return None, None, None, None, None


class _ECGWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
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
        self.refreshButton.clicked.connect(self.refresh_com)
        self.conButton.clicked.connect(self.connect)
        self.stopButton.clicked.connect(self.stop)
        self.saveButton.clicked.connect(lambda: save_data('sample.csv', self.headers, self.waveforms,
                                                          self.sampling_rate))
        self.viewButton.clicked.connect(lambda: view_data(self.waveforms, self.sampling_rate))
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
        self.sampling_rate = 0
        self.heart_rate = 0
        self.headers = ['Lead I', 'Lead II', 'Lead III', 'aVR', 'aVL', 'aVF']

        # SAMPLING PARAMETERS - USER SET. BELOW ARE THE DEFAULTS
        self.bandwidth = 160
        self.time = "5"

        # ADJUSTED BASED ON BANDWIDTH AND TIME SETTINGS
        self.R2 = 0x01
        self.R3 = 0x02
        self.points = 300
        self.adc_max = "0x800000"
        self.ODR = 0
        self.noise = 0
        self.ODR_arr = []

        # MISCELLANEOUS PARAMETERS
        self.config_name = 'config.ini'

        # SETS TAB TO CONNECTION PAGE, FOR IF THE UI FILE IS SAVED AS TO HAVE ANOTHER TAB AS DEFAULT
        self.Tabs.setCurrentIndex(2)

        # FINAL FUNCTIONS TO SETUP WINDOW
        self.populate_band()
        self.refresh_com()
        self.config = ConfigParser()
        self.load_config()

    def analysis(self):
        """
        Wrapper for analysis functions, only contains heart rate calculation currently.
        """
        self.heart_rate = pan_tompkins(self.waveforms, self.sampling_rate)
        self.heartrateLine.setText("%s bpm" % self.heart_rate)

    def load_data(self):
        """
        Loads a selected .csv file into the ECG Window
        """
        # Temporary filepath for my testing
        path = 'cardiacwaveforms.csv'
        with open(path, newline='') as csvfile:
            data_reader = csv.reader(csvfile, delimiter=',', quotechar='|')
            for i, row in enumerate(data_reader):
                if i == 0:
                    # Sampling settings
                    self.sampling_rate = float(row[1])
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
        """
        Creates the config file, and deletes the existing one if possible
        """
        open(self.config_name, 'w').close()
        self.config = ConfigParser()
        self.config.read(self.config_name)
        self.config.add_section('main')
        self.config.set('main', 'bandwidth', str(self.bandwidth))
        self.config.set('main', 'time', str(self.time))
        with open('config.ini', 'w') as config_file:
            self.config.write(config_file)

    def load_config(self):
        """
        Loads an existing config file, and creates a new one if not possible.
        """
        data = self.config.read(self.config_name)
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
                index = np.where(np.array(self.ODR_arr) == self.bandwidth)
                self.samplingrline.setCurrentIndex(int(index[0]))
                self.set_param()

    def conn_state(self, num):
        """
        Updates the ECG Window based on the connection status
        :param num: A boolean representing the connection state
        :type num: bool
        """
        if num == 0:
            self.statusLine.setText("Disconnected")
        else:
            self.statusLine.setText("Connected")
        self.Tabs.setTabEnabled(1, num)
        self.connected = num

    def connect(self):
        """
        Connects or disconnects this program to Systolic
        """
        self.port = self.comSel.currentData()
        if self.port is None or self.port == 0:
            return
        if self.connected == 1:
            try:
                self.ser.close()
                self.conn_state(False)
                return
            except serial.SerialException as exception:
                print(exception)
                self.conn_state(False)
        try:
            self.ser = serial.Serial(str(self.port), self.baud)  # open serial port
            self.conn_state(True)

        except serial.SerialException as exception:
            error = QMessageBox()
            error.setIcon(QMessageBox.Warning)
            error.setText("An error occurred when trying to connect.")
            error.setWindowTitle("Systolic")
            error.setDetailedText(f"{exception}")
            error.exec_()
            self.conn_state(True)
            return

    def refresh_com(self):
        """
        Refreshes the serial devices list on the window
        """
        self.comSel.clear()
        avail_ports = serial.tools.list_ports.comports()
        for port, desc, _ in sorted(avail_ports):
            self.comSel.addItem(desc, port)

    def update_var(self):
        """
        A function I just soley for updating the updated variable (haha)
        """
        self.updated = 1

    def populate_band(self):
        """
        Populate the bandwidth dropdown with values from the csv lookup table
        """
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
                self.ODR_arr.append(row[4])
                self.samplingrline.addItem(row[4] + " Hz", row[4])

    def set_param(self):
        """
        Gets the sampling parameters from the user's inputted values, and then writes them to config
        """
        self.updated = 0
        self.time = self.samplingline.text()
        self.bandwidth = self.samplingrline.currentData()
        self.R2, self.R3, self.adc_max, self.ODR, self.noise = value_lookup(self.bandwidth)
        self.points = int(self.time) * int(self.ODR)
        self.R2 = R2_to_Hex(float(self.R2))
        self.R3 = R3_to_Hex(float(self.R3))

        self.noiseline.setText("%s uV" % self.noise)
        self.ODRline.setText("%s Hz" % self.ODR)

        self.config.set('main', 'bandwidth', str(self.bandwidth))
        self.config.set('main', 'time', str(self.time))
        with open(self.config_name, 'w') as config_file:
            self.config.write(config_file)

    def stop(self):
        """
        Stops sampling of the ECG by sending stop command
        """
        send_data(CONFIG_REG, bin_to_hex('00000000'), self.ser)

    def start_sampling(self):
        """
        Starts sampling of the ECG by sending start command.
        Then it initiates data receiving
        """
        print(self.updated)
        if self.updated == 1:
            ret = QMessageBox.question(self, 'Warning',
                                       "You have modified your sampling parameters but have not set them. Continue?",
                                       QMessageBox.Yes | QMessageBox.No)
            if ret == QMessageBox.No:
                return
        print("ECG Measurement Init")
        self.upload()
        self.waveforms, self.sampling_rate = ecg_read(int(self.adc_max, 16), self.ser, int(self.points))

        self.viewButton.setEnabled(True)
        self.saveButton.setEnabled(True)
        self.analysisButton.setEnabled(True)
        view_data(self.waveforms, self.sampling_rate)
        # Move user to sample tab
        self.Tabs.setCurrentIndex(0)
        self.analysis()

    def upload(self):
        """
        Uploads sampling parameters to Systolic
        """
        print("Uploading decimation rates R2: %s R3: %s" % (self.R2, self.R3))
        send_data(R2_REG, self.R2, self.ser)
        send_data(R3CH1_REG, self.R3, self.ser)
        send_data(R3CH2_REG, self.R3, self.ser)
        send_data(R3CH3_REG, self.R3, self.ser)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = _ECGWindow()
    window.show()
    sys.exit(app.exec())
