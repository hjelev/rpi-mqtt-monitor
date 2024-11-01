#!/usr/bin/python

"""
from https://raw.githubusercontent.com/kif/sht21_python/refs/heads/python3/sht21.py
from https://github.com/kif/sht21_python/tree/python3
forked from jaques/sht21_python
with 

The MIT License (MIT)

Copyright (c) 2013 Richard Jaques

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""


import fcntl
import time
import unittest


class SHT21:
    """Class to read temperature and humidity from SHT21, much of class was 
    derived from:
    http://www.sensirion.com/fileadmin/user_upload/customers/sensirion/Dokumente/Humidity/Sensirion_Humidity_SHT21_Datasheet_V3.pdf
    and Martin Steppuhn's code from http://www.emsystech.de/raspi-sht21"""

    # control constants
    _SOFTRESET = 0xFE
    _I2C_ADDRESS = 0x40
    _TRIGGER_TEMPERATURE_NO_HOLD = 0xF3
    _TRIGGER_HUMIDITY_NO_HOLD = 0xF5
    _STATUS_BITS_MASK = 0xFFFC

    # From: /linux/i2c-dev.h
    I2C_SLAVE = 0x0703
    I2C_SLAVE_FORCE = 0x0706

    # datasheet (v4), page 9, table 7, thanks to Martin Milata
    # for suggesting the use of these better values
    # code copied from https://github.com/mmilata/growd
    _TEMPERATURE_WAIT_TIME = 0.086  # (datasheet: typ=66, max=85)
    _HUMIDITY_WAIT_TIME = 0.030     # (datasheet: typ=22, max=29)

    def __init__(self, device_number=0):
        """Opens the i2c device (assuming that the kernel modules have been
        loaded).  Note that this has only been tested on first revision
        raspberry pi where the device_number = 0, but it should work
        where device_number=1"""
        self.i2c = open('/dev/i2c-%s' % device_number, 'rb+', 0)
        fcntl.ioctl(self.i2c, self.I2C_SLAVE, 0x40)
        self.i2c.write(bytes([self._SOFTRESET]))
        time.sleep(0.050)

    def read_temperature(self):    
        """Reads the temperature from the sensor.  Not that this call blocks
        for ~86ms to allow the sensor to return the data"""
        self.i2c.write(bytes([self._TRIGGER_TEMPERATURE_NO_HOLD]))
        time.sleep(self._TEMPERATURE_WAIT_TIME)
        data = self.i2c.read(3)
        if self._calculate_checksum(data, 2) == data[2]:
            return self._get_temperature_from_buffer(data)

    def read_humidity(self):    
        """Reads the humidity from the sensor.  Not that this call blocks 
        for ~30ms to allow the sensor to return the data"""
        self.i2c.write(bytes([self._TRIGGER_HUMIDITY_NO_HOLD]))
        time.sleep(self._HUMIDITY_WAIT_TIME)
        data = self.i2c.read(3)
        if self._calculate_checksum(data, 2) == data[2]:
            return self._get_humidity_from_buffer(data)

    def close(self):
        """Closes the i2c connection"""
        self.i2c.close()

    def __enter__(self):
        """used to enable python's with statement support"""
        return self

    def __exit__(self, type, value, traceback):
        """with support"""
        self.close()

    @staticmethod
    def _calculate_checksum(data, number_of_bytes):
        """5.7 CRC Checksum using the polynomial given in the datasheet"""
        # CRC
        POLYNOMIAL = 0x131  # //P(x)=x^8+x^5+x^4+1 = 100110001
        crc = 0
        # calculates 8-Bit checksum with given polynomial
        for byteCtr in range(number_of_bytes):
            crc ^= data[byteCtr]
            for bit in range(8, 0, -1):
                if crc & 0x80:
                    crc = (crc << 1) ^ POLYNOMIAL
                else:
                    crc = (crc << 1)
        return crc

    @staticmethod
    def _get_temperature_from_buffer(data):
        """This function reads the first two bytes of data and
        returns the temperature in C by using the following function:
        T = -46.85 + (175.72 * (ST/2^16))
        where ST is the value from the sensor
        """
        unadjusted = (data[0] << 8) + data[1]
        unadjusted &= SHT21._STATUS_BITS_MASK  # zero the status bits
        unadjusted *= 175.72
        unadjusted /= 1 << 16  # divide by 2^16
        unadjusted -= 46.85
        return unadjusted

    @staticmethod
    def _get_humidity_from_buffer(data):
        """This function reads the first two bytes of data and returns
        the relative humidity in percent by using the following function:
        RH = -6 + (125 * (SRH / 2 ^16))
        where SRH is the value read from the sensor
        """
        unadjusted = (data[0] << 8) + data[1]
        unadjusted &= SHT21._STATUS_BITS_MASK  # zero the status bits
        unadjusted *= 125.0
        unadjusted /= 1 << 16  # divide by 2^16
        unadjusted -= 6
        return unadjusted


class SHT21Test(unittest.TestCase):
    """simple sanity test.  Run from the command line with 
    python -m unittest sht21 to check they are still good"""

    def test_temperature(self):
        """Unit test to check the checksum method"""
        calc_temp = SHT21._get_temperature_from_buffer([chr(99), chr(172)])
        self.failUnless(abs(calc_temp - 21.5653979492) < 0.1)

    def test_humidity(self):
        """Unit test to check the humidity computation using example
        from the v4 datasheet"""
        calc_temp = SHT21._get_humidity_from_buffer([chr(99), chr(82)])
        self.failUnless(abs(calc_temp - 42.4924) < 0.001)

    def test_checksum(self):
        """Unit test to check the checksum method.  Uses values read"""
        self.failUnless(SHT21._calculate_checksum([chr(99), chr(172)], 2) == 249)
        self.failUnless(SHT21._calculate_checksum([chr(99), chr(160)], 2) == 132)

if __name__ == "__main__":
    try:
        with SHT21(1) as sht21:
            print("Temperature: %s" % sht21.read_temperature())
            print("Humidity: %s" % sht21.read_humidity())
    except IOError as e:
        print(type(e), e)
        print("Error creating connection to i2c.  This must be run as root")

