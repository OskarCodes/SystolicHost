import pytest
import systolic


class TestClass:
    def test_bin_to_hex(self):
        assert systolic.bin_to_hex('00000001') == '0x01'
