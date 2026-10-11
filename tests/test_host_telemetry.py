from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.metrics.host_telemetry import gpu_thermal


class GpuThermalTests(unittest.TestCase):
    def test_peak_temperature_lowest_clock_and_reasons_seen(self):
        rows = [{'gpu': {'temperature_c': 61, 'sm_clock_mhz': 1800, 'throttle_reasons': 0x4}},
                {'gpu': {'temperature_c': 74, 'sm_clock_mhz': 1500, 'throttle_reasons': 0x20}},
                {'gpu': None}]
        self.assertEqual(gpu_thermal(rows), {'max_gpu_temperature_c': 74, 'min_sm_clock_mhz': 1500,
                                             'throttle_reasons_seen': ['sw_power_cap', 'sw_thermal']})

    def test_missing_readings_stay_unknown(self):
        rows = [{'gpu': {'utilization_percent': 90}}]
        self.assertEqual(gpu_thermal(rows), {'max_gpu_temperature_c': None, 'min_sm_clock_mhz': None,
                                             'throttle_reasons_seen': None})


if __name__ == '__main__':
    unittest.main()
