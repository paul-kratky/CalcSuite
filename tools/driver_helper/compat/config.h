/* config.h for building libwdi with MinGW-w64 from tools/build_tools.py (no autotools).
 * It stands in for the config.h libwdi's ./configure would write. WDK_DIR (the folder that
 * holds redist/wdf/x64/, from fetch_wdk_redist.py) and INSTALLER_PATH_64 (where the built
 * installer_x64.exe sits) are passed on the command line, as absolute paths.
 * SPDX-License-Identifier: LGPL-3.0-or-later */
#pragma once

#ifndef WDK_DIR
#error "WDK_DIR must be defined (see tools/driver_helper/fetch_wdk_redist.py)"
#endif

/* WinUSB only: no libusb0 / libusbK / user driver files are embedded */
#define WDF_VER 1011
#define COINSTALLER_DIR "wdf"
#define X64_DIR "x64"

/* 64-bit Windows on x64 only (Windows 10 and 11 are 64-bit; ARM64 is not built) */
#define OPT_M64 1

#define ENABLE_LOGGING 1
#define INCLUDE_DEBUG_LOGGING 1
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
