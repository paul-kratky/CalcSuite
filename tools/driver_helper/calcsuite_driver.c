/*
 * calcsuite-driver: sees which USB driver each TI calculator has, puts the WinUSB driver
 * on one (through libwdi, the library behind Zadig), or takes that driver off again so
 * Windows gives the calculator back to TI's own driver.
 *
 *   calcsuite-driver list [--probe]          TI devices Windows knows (plugged in or seen
 *                                            before) and the TI driver packages installed
 *   calcsuite-driver install-winusb PID [--dry-run] [--force] [--log FILE]
 *   calcsuite-driver restore-ti PID [--dry-run] [--log FILE]
 *   calcsuite-driver version
 *
 * PID is the USB product id in hex (e008, e004, e022, ...); the vendor is always 0451.
 * install-winusb and restore-ti change drivers and need admin rights: the program does not
 * ask for them itself (its manifest says asInvoker), the caller starts it elevated
 * (ShellExecute "runas"). An elevated process's console can't be read by the caller,
 * so --log FILE sends everything it prints to FILE as well. --dry-run changes nothing,
 * needs no admin, and prints the steps it would take.
 *
 * Output lines (stdout), one record per line:
 *   DEVICE {json}    a TI USB device node (list)
 *   PACKAGE {json}   an installed driver package (oem*.inf) that names a TI device (list)
 *   STEP text        what install/restore is doing or would do
 *   RESULT word      ok | already | nothing | dry-run (last line of install/restore)
 *   ERR code text    an error; code is a single word
 *   OK n             end of list, n devices
 * Exit codes: 0 done, 1 usage, 2 no such device, 3 failed, 4 needs admin rights.
 *
 * Copyright (c) 2026 CalcSuite contributors.
 * SPDX-License-Identifier: LGPL-3.0-or-later
 * Links libwdi (LGPL-3.0-or-later, third_party/libwdi) statically; this program's whole
 * source is in this repository, so it can be rebuilt against a changed libwdi.
 */

#define INITGUID
#include <windows.h>
#include <cfgmgr32.h>
#include <devpkey.h>
#include <io.h>
#include <setupapi.h>
#include <shlobj.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "libwdi.h"

#define TI_VID 0x0451
#define HELPER_VERSION "1.0.0"

typedef struct {
    unsigned pid;
    const char *name;
} Model;

/* The TI link devices this helper will touch. Anything else is refused. */
static const Model MODELS[] = {
    {0xe008, "TI-84 Plus CE"},  /* also 84 Plus C Silver Edition, 83 Premium CE, newer 84 Plus */
    {0xe004, "TI-89 Titanium"}, /* also the TI-84 Plus (Silver Edition) on older boot code */
    {0xe003, "TI-84 Plus"},
    {0xe022, "TI-Nspire CX II"},
    {0xe012, "TI-Nspire"},
};
#define N_MODELS (sizeof(MODELS) / sizeof(MODELS[0]))

static const char *model_name(unsigned pid) {
    for (size_t i = 0; i < N_MODELS; i++)
        if (MODELS[i].pid == pid) return MODELS[i].name;
    return NULL;
}

/* ---------- small output helpers ---------- */

static void json_str(const char *key, const char *v, int comma) {
    printf("%s\"%s\":", comma ? "," : "", key);
    if (!v) {
        printf("null");
        return;
    }
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)v; *p; p++) {
        if (*p == '"' || *p == '\\')
            printf("\\%c", *p);
        else if (*p < 0x20)
            printf("\\u%04x", *p);
        else
            putchar(*p);
    }
    putchar('"');
}

static void json_int(const char *key, long v) { printf(",\"%s\":%ld", key, v); }

static void json_bool(const char *key, int v) { printf(",\"%s\":%s", key, v ? "true" : "false"); }

static void step(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    printf("STEP ");
    vprintf(fmt, ap);
    printf("\n");
    va_end(ap);
    fflush(stdout);
}

static int err(int rc, const char *code, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    printf("ERR %s ", code);
    vprintf(fmt, ap);
    printf("\n");
    va_end(ap);
    fflush(stdout);
    return rc;
}

static int is_elevated(void) { return IsUserAnAdmin() ? 1 : 0; }

/* strlcpy: copies what fits and always ends the string */
static void copy_str(char *dst, size_t n, const char *src) {
    size_t len = strlen(src);
    if (len >= n) len = n - 1;
    memcpy(dst, src, len);
    dst[len] = 0;
}

/* DiUninstallDevice (newdev.dll, Windows 7+) is missing from MinGW's import library */
typedef BOOL(WINAPI *DiUninstallDeviceFn)(HWND, HDEVINFO, PSP_DEVINFO_DATA, DWORD, PBOOL);

static BOOL uninstall_device(HDEVINFO set, SP_DEVINFO_DATA *dd, BOOL *reboot) {
    HMODULE m = LoadLibraryExA("newdev.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!m) return FALSE;
    DiUninstallDeviceFn fn =
        (DiUninstallDeviceFn)(void (*)(void))GetProcAddress(m, "DiUninstallDevice");
    BOOL ok = fn ? fn(NULL, set, dd, 0, reboot) : FALSE;
    DWORD e = GetLastError();
    FreeLibrary(m);
    SetLastError(e);
    return ok;
}

/* ---------- device nodes ---------- */

typedef struct {
    char instance[256];
    unsigned pid;
    int present;
    char desc[256];
    char service[64];
    char inf[64];
    char provider[128];
    char driver_version[64];
    char iface_guid[64];
    char last_arrival[32];
    unsigned long problem;
    int has_problem;
    int started;
    char access[24]; /* free | busy | not-probed | n/a | error-N */
} Node;

static void reg_str(HKEY k, const char *name, char *out, size_t n) {
    DWORD type = 0, size = (DWORD)n - 1;
    out[0] = 0;
    if (RegQueryValueExA(k, name, NULL, &type, (BYTE *)out, &size) == ERROR_SUCCESS &&
        (type == REG_SZ || type == REG_MULTI_SZ || type == REG_EXPAND_SZ))
        out[size < n ? size : n - 1] = 0; /* a REG_MULTI_SZ keeps its first string */
    else
        out[0] = 0;
}

static void prop_str(HDEVINFO set, SP_DEVINFO_DATA *dd, DWORD prop, char *out, size_t n) {
    out[0] = 0;
    if (!SetupDiGetDeviceRegistryPropertyA(set, dd, prop, NULL, (BYTE *)out, (DWORD)n - 1, NULL))
        out[0] = 0;
    out[n - 1] = 0;
}

/* "USB\VID_0451&PID_E008\..." -> pid, or 0 when it is not a plain TI device node */
static unsigned ti_pid_of(const char *instance) {
    if (_strnicmp(instance, "USB\\VID_0451&PID_", 17) != 0) return 0;
    char hex[5];
    memcpy(hex, instance + 17, 4);
    hex[4] = 0;
    char *end = NULL;
    unsigned long pid = strtoul(hex, &end, 16);
    if (!end || *end) return 0;
    return (unsigned)pid;
}

static void probe_access(Node *n) {
    if (!n->present || !n->iface_guid[0] || _stricmp(n->service, "WinUSB") != 0) {
        strcpy(n->access, "n/a");
        return;
    }
    WCHAR wguid[64];
    GUID guid;
    MultiByteToWideChar(CP_ACP, 0, n->iface_guid, -1, wguid, 64);
    if (CLSIDFromString(wguid, &guid) != NOERROR) {
        strcpy(n->access, "n/a");
        return;
    }
    ULONG len = 0;
    if (CM_Get_Device_Interface_List_SizeA(&len, &guid, n->instance,
                                           CM_GET_DEVICE_INTERFACE_LIST_PRESENT) != CR_SUCCESS ||
        len < 2) {
        strcpy(n->access, "n/a");
        return;
    }
    char *buf = calloc(len, 1);
    if (!buf) return;
    if (CM_Get_Device_Interface_ListA(&guid, n->instance, buf, len,
                                      CM_GET_DEVICE_INTERFACE_LIST_PRESENT) == CR_SUCCESS &&
        buf[0]) {
        /* WinUSB allows one open handle: another program holding it gives access denied.
           Opening sends nothing to the calculator; the handle is closed at once. */
        HANDLE h = CreateFileA(buf, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                               NULL, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, NULL);
        if (h != INVALID_HANDLE_VALUE) {
            CloseHandle(h);
            strcpy(n->access, "free");
        } else if (GetLastError() == ERROR_ACCESS_DENIED) {
            strcpy(n->access, "busy");
        } else {
            snprintf(n->access, sizeof(n->access), "error-%lu", GetLastError());
        }
    } else {
        strcpy(n->access, "n/a");
    }
    free(buf);
}

static void fill_node(HDEVINFO set, SP_DEVINFO_DATA *dd, Node *n, int probe) {
    ULONG st = 0, prob = 0;
    n->present = CM_Get_DevNode_Status(&st, &prob, dd->DevInst, 0) == CR_SUCCESS;
    n->has_problem = n->present && (st & DN_HAS_PROBLEM);
    n->problem = n->has_problem ? prob : 0;
    n->started = n->present && (st & DN_STARTED);
    prop_str(set, dd, SPDRP_FRIENDLYNAME, n->desc, sizeof(n->desc));
    if (!n->desc[0]) prop_str(set, dd, SPDRP_DEVICEDESC, n->desc, sizeof(n->desc));
    prop_str(set, dd, SPDRP_SERVICE, n->service, sizeof(n->service));
    HKEY k = SetupDiOpenDevRegKey(set, dd, DICS_FLAG_GLOBAL, 0, DIREG_DRV, KEY_READ);
    if (k != INVALID_HANDLE_VALUE) {
        reg_str(k, "InfPath", n->inf, sizeof(n->inf));
        reg_str(k, "ProviderName", n->provider, sizeof(n->provider));
        reg_str(k, "DriverVersion", n->driver_version, sizeof(n->driver_version));
        RegCloseKey(k);
    }
    k = SetupDiOpenDevRegKey(set, dd, DICS_FLAG_GLOBAL, 0, DIREG_DEV, KEY_READ);
    if (k != INVALID_HANDLE_VALUE) {
        reg_str(k, "DeviceInterfaceGUIDs", n->iface_guid, sizeof(n->iface_guid));
        if (!n->iface_guid[0]) reg_str(k, "DeviceInterfaceGUID", n->iface_guid, sizeof(n->iface_guid));
        RegCloseKey(k);
    }
    DEVPROPTYPE type = 0;
    FILETIME ft;
    if (SetupDiGetDevicePropertyW(set, dd, &DEVPKEY_Device_LastArrivalDate, &type, (BYTE *)&ft,
                                  sizeof(ft), NULL, 0) &&
        type == DEVPROP_TYPE_FILETIME) {
        SYSTEMTIME s;
        if (FileTimeToSystemTime(&ft, &s))
            snprintf(n->last_arrival, sizeof(n->last_arrival), "%04u-%02u-%02uT%02u:%02u:%02uZ",
                     s.wYear % 10000u, s.wMonth % 100u, s.wDay % 100u, s.wHour % 100u,
                     s.wMinute % 100u, s.wSecond % 100u);
    }
    if (probe)
        probe_access(n);
    else
        strcpy(n->access, "not-probed");
}

typedef int (*NodeFn)(HDEVINFO set, SP_DEVINFO_DATA *dd, Node *n, void *ctx);

/* Calls fn for every TI device node under USB, plugged in or not (want_pid 0: all) */
static int for_each_node(unsigned want_pid, int probe, NodeFn fn, void *ctx) {
    HDEVINFO set = SetupDiGetClassDevsA(NULL, "USB", NULL, DIGCF_ALLCLASSES);
    if (set == INVALID_HANDLE_VALUE) return -1;
    int count = 0;
    SP_DEVINFO_DATA dd;
    dd.cbSize = sizeof(dd);
    for (DWORD i = 0; SetupDiEnumDeviceInfo(set, i, &dd); i++) {
        Node n;
        memset(&n, 0, sizeof(n));
        if (!SetupDiGetDeviceInstanceIdA(set, &dd, n.instance, sizeof(n.instance), NULL)) continue;
        n.pid = ti_pid_of(n.instance);
        if (!n.pid || strstr(n.instance, "&MI_")) continue;
        if (want_pid && n.pid != want_pid) continue;
        fill_node(set, &dd, &n, probe);
        count++;
        if (fn && fn(set, &dd, &n, ctx)) break;
    }
    SetupDiDestroyDeviceInfoList(set);
    return count;
}

static int print_node(HDEVINFO set, SP_DEVINFO_DATA *dd, Node *n, void *ctx) {
    (void)set;
    (void)dd;
    (void)ctx;
    char pid[8];
    snprintf(pid, sizeof(pid), "%04x", n->pid);
    printf("DEVICE {");
    json_str("pid", pid, 0);
    json_str("model", model_name(n->pid), 1);
    json_str("instance", n->instance, 1);
    json_bool("present", n->present);
    json_bool("started", n->started);
    json_int("problem", (long)n->problem);
    json_str("desc", n->desc, 1);
    json_str("service", n->service[0] ? n->service : NULL, 1);
    json_str("inf", n->inf[0] ? n->inf : NULL, 1);
    json_str("provider", n->provider[0] ? n->provider : NULL, 1);
    json_str("driver_version", n->driver_version[0] ? n->driver_version : NULL, 1);
    json_str("last_arrival", n->last_arrival[0] ? n->last_arrival : NULL, 1);
    json_str("access", n->access, 1);
    printf("}\n");
    return 0;
}

/* ---------- driver packages (C:\Windows\INF\oem*.inf) ---------- */

typedef struct {
    char name[64];     /* oem12.inf */
    char provider[128];
    char cls[64];
    char version[96];
    unsigned pids[8];
    int npids;
    int ours; /* made by libwdi (CalcSuite or Zadig) */
} Package;

/* Reads an .inf as upper-case ASCII (UTF-16LE files have their zero bytes dropped) */
static char *read_inf_upper(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size <= 0 || size > 8 * 1024 * 1024) {
        fclose(f);
        return NULL;
    }
    unsigned char *raw = malloc((size_t)size + 1);
    if (!raw) {
        fclose(f);
        return NULL;
    }
    size_t got = fread(raw, 1, (size_t)size, f);
    fclose(f);
    char *out = malloc(got + 1);
    if (!out) {
        free(raw);
        return NULL;
    }
    int utf16 = got >= 2 && raw[0] == 0xff && raw[1] == 0xfe;
    size_t o = 0;
    for (size_t i = utf16 ? 2 : 0; i < got; i += utf16 ? 2 : 1) {
        unsigned char c = raw[i];
        if (utf16 && i + 1 < got && raw[i + 1]) c = '?';
        out[o++] = (c >= 'a' && c <= 'z') ? (char)(c - 32) : (char)c;
    }
    out[o] = 0;
    free(raw);
    return out;
}

static void inf_field(HINF h, const char *section, const char *key, char *out, size_t n) {
    INFCONTEXT ctx;
    out[0] = 0;
    if (SetupFindFirstLineA(h, section, key, &ctx)) {
        if (!SetupGetLineTextA(&ctx, NULL, NULL, NULL, out, (DWORD)n, NULL)) out[0] = 0;
    }
}

typedef int (*PackageFn)(const Package *p, void *ctx);

static int for_each_package(PackageFn fn, void *ctx) {
    char dir[MAX_PATH], pattern[2 * MAX_PATH];
    if (!GetWindowsDirectoryA(dir, sizeof(dir))) return -1;
    snprintf(pattern, sizeof(pattern), "%s\\INF\\oem*.inf", dir);
    WIN32_FIND_DATAA fd;
    HANDLE fh = FindFirstFileA(pattern, &fd);
    if (fh == INVALID_HANDLE_VALUE) return 0;
    int count = 0;
    do {
        char path[3 * MAX_PATH];
        snprintf(path, sizeof(path), "%s\\INF\\%s", dir, fd.cFileName);
        char *text = read_inf_upper(path);
        if (!text) continue;
        Package p;
        memset(&p, 0, sizeof(p));
        for (const char *s = text; (s = strstr(s, "VID_0451&PID_")) != NULL; s += 13) {
            char hex[5];
            memcpy(hex, s + 13, 4);
            hex[4] = 0;
            char *end = NULL;
            unsigned pid = (unsigned)strtoul(hex, &end, 16);
            if (!end || *end) continue;
            int dup = 0;
            for (int i = 0; i < p.npids; i++) dup |= p.pids[i] == pid;
            if (!dup && p.npids < 8) p.pids[p.npids++] = pid;
        }
        free(text);
        if (!p.npids) continue;
        copy_str(p.name, sizeof(p.name), fd.cFileName);
        HINF h = SetupOpenInfFileA(path, NULL, INF_STYLE_WIN4, NULL);
        if (h != INVALID_HANDLE_VALUE) {
            inf_field(h, "Version", "Provider", p.provider, sizeof(p.provider));
            inf_field(h, "Version", "Class", p.cls, sizeof(p.cls));
            inf_field(h, "Version", "DriverVer", p.version, sizeof(p.version));
            SetupCloseInfFile(h);
        }
        p.ours = _stricmp(p.provider, "libwdi") == 0;
        count++;
        if (fn && fn(&p, ctx)) break;
    } while (FindNextFileA(fh, &fd));
    FindClose(fh);
    return count;
}

static int package_has_pid(const Package *p, unsigned pid) {
    for (int i = 0; i < p->npids; i++)
        if (p->pids[i] == pid) return 1;
    return 0;
}

static int print_package(const Package *p, void *ctx) {
    (void)ctx;
    printf("PACKAGE {");
    json_str("inf", p->name, 0);
    json_str("provider", p->provider, 1);
    json_str("class", p->cls, 1);
    json_str("version", p->version, 1);
    printf(",\"pids\":[");
    for (int i = 0; i < p->npids; i++) printf("%s\"%04x\"", i ? "," : "", p->pids[i]);
    printf("]");
    json_bool("ours", p->ours);
    printf("}\n");
    return 0;
}

static int cmd_list(int probe) {
    int n = for_each_node(0, probe, print_node, NULL);
    if (n < 0) return err(3, "setupapi", "SetupDiGetClassDevs failed (%lu)", GetLastError());
    for_each_package(print_package, NULL);
    printf("OK %d\n", n);
    return 0;
}

/* ---------- install-winusb ---------- */

typedef struct {
    unsigned pid;
    int present;
    char service[64];
} Seen;

static int remember_present(HDEVINFO set, SP_DEVINFO_DATA *dd, Node *n, void *ctx) {
    (void)set;
    (void)dd;
    Seen *s = ctx;
    if (!n->present) return 0;
    s->present = 1;
    copy_str(s->service, sizeof(s->service), n->service[0] ? n->service : "none");
    return 1;
}

static void temp_dir(unsigned pid, char *out, size_t n) {
    char tmp[MAX_PATH + 1];
    if (!GetTempPathA(MAX_PATH, tmp)) strcpy(tmp, ".\\");
    snprintf(out, n, "%sCalcSuite-driver\\%04x", tmp, pid);
}

static void show_inf(const char *dir, const char *inf) {
    char path[3 * MAX_PATH];
    snprintf(path, sizeof(path), "%s\\%s", dir, inf);
    /* libwdi writes the .inf as UTF-16: let SetupAPI read it */
    HINF h = SetupOpenInfFileA(path, NULL, INF_STYLE_WIN4, NULL);
    if (h == INVALID_HANDLE_VALUE) {
        step("  (could not read back %s: error %lu)", path, GetLastError());
        return;
    }
    static const char *const keys[][2] = {
        {"Strings", "DeviceName"}, {"Strings", "VendorName"},  {"Strings", "DeviceID"},
        {"Version", "Provider"},   {"Version", "DriverVer"},   {"Version", "CatalogFile"},
    };
    for (size_t i = 0; i < sizeof(keys) / sizeof(keys[0]); i++) {
        char v[256];
        inf_field(h, keys[i][0], keys[i][1], v, sizeof(v));
        step("  inf %s = %s", keys[i][1], v[0] ? v : "(none)");
    }
    SetupCloseInfFile(h);
}

static int cmd_install(unsigned pid, int dry_run, int force) {
    const char *name = model_name(pid);
    if (!name) return err(1, "unknown-pid", "%04x is not a TI calculator this helper knows", pid);
    struct wdi_device_info *list = NULL, *found = NULL;
    struct wdi_options_create_list ocl = {TRUE, FALSE, TRUE};
    int r = wdi_create_list(&list, &ocl);
    if (r != WDI_SUCCESS && r != WDI_ERROR_NO_DEVICE)
        return err(3, "wdi-list", "%s", wdi_strerror(r));
    for (struct wdi_device_info *d = list; d; d = d->next)
        if (d->vid == TI_VID && d->pid == pid && !d->is_composite) found = d;
    if (!found) {
        if (list) wdi_destroy_list(list);
        return err(2, "not-found", "no %s (0451:%04x) is plugged in and switched on", name, pid);
    }
    step("found %s (0451:%04x), driver now: %s", name, pid, found->driver ? found->driver : "none");
    if (found->driver && !_stricmp(found->driver, "WinUSB") && !force) {
        wdi_destroy_list(list);
        printf("RESULT already\n");
        return 0;
    }
    if (!dry_run && !is_elevated()) {
        wdi_destroy_list(list);
        return err(4, "needs-admin", "installing a driver needs admin rights (start it elevated)");
    }
    struct wdi_device_info dev = *found;
    char desc[96];
    snprintf(desc, sizeof(desc), "%s", name);
    dev.desc = desc;
    dev.next = NULL;
    char dir[2 * MAX_PATH], inf[64];
    temp_dir(pid, dir, sizeof(dir));
    snprintf(inf, sizeof(inf), "calcsuite_ti_%04x.inf", pid);
    struct wdi_options_prepare_driver opd;
    memset(&opd, 0, sizeof(opd));
    opd.driver_type = WDI_WINUSB;
    opd.vendor_name = "Texas Instruments";
    opd.disable_signing = dry_run ? TRUE : FALSE; /* signing adds a certificate to the system */
    step("write a WinUSB driver package for USB\\VID_0451&PID_%04X to %s\\%s", pid, dir, inf);
    if (!dry_run)
        step("self-sign its catalog with a new certificate (libwdi adds it to the machine's"
             " Trusted Root and Trusted Publisher stores; its private key is thrown away)");
    r = wdi_prepare_driver(&dev, dir, inf, &opd);
    if (r != WDI_SUCCESS) {
        wdi_destroy_list(list);
        return err(3, "prepare", "%s", wdi_strerror(r));
    }
    show_inf(dir, inf);
    if (dry_run) {
        step("would install it on %s (Windows then gives the calculator WinUSB; TI's driver"
             " stays in the driver store but no longer owns this device)",
             dev.device_id ? dev.device_id : "the device");
        wdi_destroy_list(list);
        printf("RESULT dry-run\n");
        return 0;
    }
    struct wdi_options_install_driver oid;
    memset(&oid, 0, sizeof(oid));
    oid.pending_install_timeout = 120000;
    step("install it on %s", dev.device_id ? dev.device_id : "the device");
    r = wdi_install_driver(&dev, dir, inf, &oid);
    wdi_destroy_list(list);
    if (r != WDI_SUCCESS) return err(3, "install", "%s", wdi_strerror(r));
    Seen s;
    memset(&s, 0, sizeof(s));
    for_each_node(pid, 0, remember_present, &s);
    step("driver now: %s", s.present ? s.service : "(device gone)");
    printf("RESULT ok\n");
    return 0;
}

/* ---------- restore-ti ---------- */

#define MAX_ITEMS 32

typedef struct {
    unsigned pid;
    char nodes[MAX_ITEMS][256];
    int nnodes;
    char ours[MAX_ITEMS][64];
    int nours;
    char ti[MAX_ITEMS][64];
    int nti;
} Plan;

static int plan_node(HDEVINFO set, SP_DEVINFO_DATA *dd, Node *n, void *ctx) {
    (void)set;
    (void)dd;
    Plan *p = ctx;
    if (_stricmp(n->provider, "libwdi") != 0) {
        step("leave %s alone: its driver is %s (%s)", n->instance,
             n->service[0] ? n->service : "none", n->provider[0] ? n->provider : "no package");
        return 0;
    }
    if (p->nnodes < MAX_ITEMS) copy_str(p->nodes[p->nnodes++], sizeof(p->nodes[0]), n->instance);
    return 0;
}

static int plan_package(const Package *pk, void *ctx) {
    Plan *p = ctx;
    if (!package_has_pid(pk, p->pid)) return 0;
    if (pk->ours && p->nours < MAX_ITEMS)
        copy_str(p->ours[p->nours++], sizeof(p->ours[0]), pk->name);
    else if (!pk->ours && p->nti < MAX_ITEMS)
        copy_str(p->ti[p->nti++], sizeof(p->ti[0]), pk->name);
    if (!pk->ours) step("driver package %s from \"%s\" (%s) also names this device", pk->name,
                        pk->provider, pk->version);
    return 0;
}

static int uninstall_node(HDEVINFO set, SP_DEVINFO_DATA *dd, Node *n, void *ctx) {
    Plan *p = ctx;
    for (int i = 0; i < p->nnodes; i++) {
        if (strcmp(p->nodes[i], n->instance) != 0) continue;
        BOOL reboot = FALSE;
        if (uninstall_device(set, dd, &reboot))
            step("removed device %s%s", n->instance, reboot ? " (Windows wants a restart)" : "");
        else
            step("could not remove device %s (error %lu)", n->instance, GetLastError());
    }
    return 0;
}

static int cmd_restore(unsigned pid, int dry_run) {
    const char *name = model_name(pid);
    if (!name) return err(1, "unknown-pid", "%04x is not a TI calculator this helper knows", pid);
    Plan plan;
    memset(&plan, 0, sizeof(plan));
    plan.pid = pid;
    for_each_node(pid, 0, plan_node, &plan);
    for_each_package(plan_package, &plan);
    if (!plan.nnodes && !plan.nours) {
        step("no WinUSB driver from libwdi (CalcSuite or Zadig) is set up for the %s", name);
        printf("RESULT nothing\n");
        return 0;
    }
    if (!dry_run && !is_elevated())
        return err(4, "needs-admin", "removing a driver needs admin rights (start it elevated)");
    const char *verb = dry_run ? "would " : "";
    for (int i = 0; i < plan.nnodes; i++)
        step("%sremove device %s (its WinUSB setup goes; a plugged-in calculator drops off USB"
             " for a moment)", verb, plan.nodes[i]);
    for (int i = 0; i < plan.nours; i++)
        step("%sdelete driver package %s (libwdi's WinUSB package for this calculator)", verb,
             plan.ours[i]);
    step("%sscan for hardware, so Windows picks the best driver it has left", verb);
    if (plan.nti)
        step("TI's driver package is installed (%s): Windows should give the calculator to it",
             plan.ti[0]);
    else
        step("no TI driver package is installed: the calculator will show without a driver"
             " until TI Connect CE (or TI's other software) is installed again");
    if (dry_run) {
        printf("RESULT dry-run\n");
        return 0;
    }
    for_each_node(pid, 0, uninstall_node, &plan);
    for (int i = 0; i < plan.nours; i++) {
        if (SetupUninstallOEMInfA(plan.ours[i], SUOI_FORCEDELETE, NULL))
            step("deleted %s", plan.ours[i]);
        else
            step("could not delete %s (error %lu)", plan.ours[i], GetLastError());
    }
    DEVINST root;
    if (CM_Locate_DevNodeA(&root, NULL, CM_LOCATE_DEVNODE_NORMAL) == CR_SUCCESS)
        CM_Reenumerate_DevNode(root, CM_REENUMERATE_SYNCHRONOUS | CM_REENUMERATE_RETRY_INSTALLATION);
    Seen s;
    memset(&s, 0, sizeof(s));
    for (int t = 0; t < 30; t++) { /* up to 15 s for the device to come back */
        memset(&s, 0, sizeof(s));
        for_each_node(pid, 0, remember_present, &s);
        if (s.present && strcmp(s.service, "none") != 0) break;
        Sleep(500);
    }
    step("driver now: %s", s.present ? s.service : "(not plugged in)");
    printf("RESULT ok\n");
    return 0;
}

/* ---------- main ---------- */

static int usage(void) {
    printf("usage: calcsuite-driver list [--probe]\n"
           "       calcsuite-driver install-winusb PID [--dry-run] [--force] [--log FILE]\n"
           "       calcsuite-driver restore-ti PID [--dry-run] [--log FILE]\n"
           "       calcsuite-driver version\n");
    return 1;
}

static int parse_pid(const char *s, unsigned *pid) {
    if (!_strnicmp(s, "0x", 2)) s += 2;
    char *end = NULL;
    unsigned long v = strtoul(s, &end, 16);
    if (!*s || !end || *end || v == 0 || v > 0xffff) return 0;
    *pid = (unsigned)v;
    return 1;
}

int main(int argc, char **argv) {
    int dry_run = 0, force = 0, probe = 0;
    const char *log = NULL;
    const char *pos[4] = {0};
    int npos = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--dry-run"))
            dry_run = 1;
        else if (!strcmp(argv[i], "--force"))
            force = 1;
        else if (!strcmp(argv[i], "--probe"))
            probe = 1;
        else if (!strcmp(argv[i], "--log") && i + 1 < argc)
            log = argv[++i];
        else if (argv[i][0] == '-' || npos >= 4)
            return usage();
        else
            pos[npos++] = argv[i];
    }
    if (log) {
        if (!freopen(log, "w", stdout)) return 3;
        _dup2(_fileno(stdout), _fileno(stderr));
    }
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    if (!npos) return usage();
    wdi_set_log_level(WDI_LOG_LEVEL_WARNING);
    if (!strcmp(pos[0], "version") && npos == 1) {
        VS_FIXEDFILEINFO fi;
        memset(&fi, 0, sizeof(fi));
        int winusb = wdi_is_driver_supported(WDI_WINUSB, &fi);
        printf("calcsuite-driver %s, libwdi with WinUSB %s, elevated %s\n", HELPER_VERSION,
               winusb ? "embedded" : "MISSING", is_elevated() ? "yes" : "no");
        return winusb ? 0 : 3;
    }
    if (!strcmp(pos[0], "list") && npos == 1) return cmd_list(probe);
    unsigned pid = 0;
    if (npos == 2 && !parse_pid(pos[1], &pid)) return usage();
    if (!strcmp(pos[0], "install-winusb") && npos == 2) return cmd_install(pid, dry_run, force);
    if (!strcmp(pos[0], "restore-ti") && npos == 2) return cmd_restore(pid, dry_run);
    return usage();
}
