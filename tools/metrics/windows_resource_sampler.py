"""Read-only Windows telemetry for a bound Strata installation; no credentials."""
import ctypes
import json
import os
from pathlib import Path
import sys
import time


def sample(root, output, stop):
    import psutil
    class Memory(ctypes.Structure):
        _fields_=[('total',ctypes.c_ulonglong),('free',ctypes.c_ulonglong),('used',ctypes.c_ulonglong)]
    class Utilization(ctypes.Structure):
        _fields_=[('gpu',ctypes.c_uint),('memory',ctypes.c_uint)]
    nvml=None;handle=ctypes.c_void_p()
    try:
        nvml=ctypes.WinDLL('nvml.dll')
        if nvml.nvmlInit_v2()!=0 or nvml.nvmlDeviceGetHandleByIndex_v2(0,ctypes.byref(handle))!=0:nvml=None
    except (OSError,AttributeError):pass
    expected=os.path.normcase(str(Path(root)/'runtime/Strata/engine/strata.exe'))
    previous={};psutil.cpu_percent();started=time.monotonic()
    with Path(output).open('x',encoding='utf-8') as stream:
        while not Path(stop).exists() and time.monotonic()-started<1800:
            at=time.time();vm=psutil.virtual_memory()
            row={'at':at,'cpu_percent':psutil.cpu_percent(),'available_ram_bytes':vm.available,
                 'ram_used_bytes':vm.total-vm.available,'model_processes':[],'gpu':None}
            freq=psutil.cpu_freq();row['cpu_frequency_mhz']=freq.current if freq else None
            for p in psutil.process_iter(['pid','exe']):
                try:
                    if os.path.normcase(p.info['exe'] or '')!=expected:continue
                    m=p.memory_info();t=p.cpu_times();total=t.user+t.system;old=previous.get(p.pid)
                    row['model_processes'].append({'pid':p.pid,'working_set_bytes':m.rss,
                        'private_bytes':getattr(m,'private',None),'page_fault_count':getattr(m,'num_page_faults',None),
                        'cpu_percent_of_machine':(100*(total-old[1])/(at-old[0])/psutil.cpu_count() if old and at>old[0] else None)})
                    previous[p.pid]=(at,total)
                except (psutil.Error,OSError):continue
            if nvml:
                mem=Memory();util=Utilization()
                if nvml.nvmlDeviceGetMemoryInfo(handle,ctypes.byref(mem))==0 and nvml.nvmlDeviceGetUtilizationRates(handle,ctypes.byref(util))==0:
                    row['gpu']={'used_bytes':mem.used,'free_bytes':mem.free,'total_bytes':mem.total,'utilization_percent':util.gpu}
                    # Thermal evidence: core temperature, SM clock, and NVML's active clock-limiting reasons.
                    temperature=ctypes.c_uint();clock=ctypes.c_uint();reasons=ctypes.c_ulonglong()
                    row['gpu']['temperature_c']=temperature.value if nvml.nvmlDeviceGetTemperature(handle,0,ctypes.byref(temperature))==0 else None
                    row['gpu']['sm_clock_mhz']=clock.value if nvml.nvmlDeviceGetClockInfo(handle,1,ctypes.byref(clock))==0 else None
                    row['gpu']['throttle_reasons']=reasons.value if nvml.nvmlDeviceGetCurrentClocksThrottleReasons(handle,ctypes.byref(reasons))==0 else None
                    # Board power draw (NVML averages it over its own short window) and memory clock, for power-related resets.
                    power=ctypes.c_uint();mem_clock=ctypes.c_uint()
                    row['gpu']['power_w']=power.value/1000 if nvml.nvmlDeviceGetPowerUsage(handle,ctypes.byref(power))==0 else None
                    row['gpu']['mem_clock_mhz']=mem_clock.value if nvml.nvmlDeviceGetClockInfo(handle,2,ctypes.byref(mem_clock))==0 else None
            stream.write(json.dumps(row)+'\n');stream.flush();time.sleep(1)
    if nvml:nvml.nvmlShutdown()


if __name__=='__main__':sample(*sys.argv[1:])
