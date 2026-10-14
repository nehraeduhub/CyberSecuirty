#!/usr/bin/env python3
"""TEST HARNESS ONLY: record a utmp login for an X display so `who` shows a console user (as on a real PC)."""
import ctypes, ctypes.util, subprocess, sys, time

class ExitStatus(ctypes.Structure):
    _fields_ = [('e_termination', ctypes.c_short), ('e_exit', ctypes.c_short)]

class TimeVal(ctypes.Structure):
    _fields_ = [('tv_sec', ctypes.c_int32), ('tv_usec', ctypes.c_int32)]

class Utmpx(ctypes.Structure):
    _fields_ = [('ut_type', ctypes.c_short), ('ut_pid', ctypes.c_int), ('ut_line', ctypes.c_char * 32), ('ut_id', ctypes.c_char * 4),
                ('ut_user', ctypes.c_char * 32), ('ut_host', ctypes.c_char * 256), ('ut_exit', ExitStatus), ('ut_session', ctypes.c_int32),
                ('ut_tv', TimeVal), ('ut_addr_v6', ctypes.c_int32 * 4), ('unused', ctypes.c_char * 20)]

display = sys.argv[1]
pid = int((subprocess.run(['pgrep', '-f', f'Xvfb {display}'], capture_output=True, text=True).stdout.split() or ['1'])[0])
libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
u = Utmpx(ut_type=7, ut_pid=pid, ut_line=display.encode(), ut_id=display[-4:].encode(), ut_user=b'root', ut_host=display.encode(),
          ut_tv=TimeVal(int(time.time()), 0))
libc.setutxent(); libc.pututxline(ctypes.byref(u)); libc.endutxent()
