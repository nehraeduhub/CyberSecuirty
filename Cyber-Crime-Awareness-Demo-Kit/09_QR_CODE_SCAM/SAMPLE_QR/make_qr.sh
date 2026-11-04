#!/usr/bin/env bash
set -u
mk(){ if command -v qrencode>/dev/null 2>&1; then qrencode -o "$2" -s 8 -m 2 "$1" && echo "wrote $2"; else echo "Install qrencode: sudo apt install qrencode"; fi; }
mk "SIMULATED DEMO QR — awareness only" demo_safe.png
