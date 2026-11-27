// SPDX-License-Identifier: GPL-3.0-or-later
/*
 * ti84-cli: a small USB link for the TI-84 Plus CE family and the TI-89 Titanium (TI's "DUSB"
 * protocol) on libusb.
 *
 *   ti84-cli [--model M] info           connect and print the model, OS version and free memory
 *   ti84-cli [--model M] shot FILE.ppm  save the screen as a PPM picture
 *   ti84-cli [--model M] key HEXCODE    press one key (see ti84_keys.py / ti89_keys.py)
 *   ti84-cli [--model M] clock          print the calculator's date and time
 *   ti84-cli [--model M] serve          one connection, commands on stdin, one per line:
 *                                       info | shot FILE | key HEX | keys HEX HEX ... |
 *                                       ls | get TYPE FOLDERHEX NAMEHEX SIZE LOCAL |
 *                                       send FILE (a TI file: .8xp .8xv ... or .89p .89e ...) |
 *                                       put TYPE ARCH VERSION NAMEHEX LOCAL (84 only) |
 *                                       rm TYPE NAMEHEX [FOLDERHEX] (the 89 needs it) |
 *                                       clock | setclock now|YYYY MM DD hh mm ss |
 *                                       home | exec prgm|asm FOLDERHEX NAMEHEX (89) |
 *                                       romdump LOCAL (a ROM dumper already running) | quit
 *                                       each ends with "END <code>" (as nspire-cli serve does);
 *                                       names travel as hex, transfers print PROGRESS lines
 *   ti84-cli [--model M] send FILE      send every variable in a TI file (one that has the
 *                                       name of one on the calculator replaces it)
 *   ti84-cli devices                    list the TI calculators on USB (opens none of them)
 *
 * Which calculator: --model 84ce (USB id 0451:E008), 89t (0451:E004) or auto (the first of
 * either that is found). Without --model the program's name decides: the copy named
 * ti89-cli.exe talks to a TI-89 Titanium only, ti84-cli.exe to the TI-84 Plus family only (so
 * two windows of the mirror never take each other's calculator).
 *
 * Exit codes: 0 ok, 1 usage error, 2 no calculator found, 3 driver/open problem,
 *             4 link/protocol error, 6 local file error.
 *
 * The protocol (raw packets, virtual packets, the mode handshake, parameter requests, the
 * remote key command) follows what TILP's libticalcs does (dusb_rpkt.cc, dusb_vpkt.cc,
 * dusb_cmd.cc, calc_84p.cc; GPL-2.0-or-later, https://github.com/debrouxl/tilibs). This
 * file is our own code for it, under GPL-3.0-or-later.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#define sleep_ms(x) Sleep(x)
#else
#include <unistd.h>
#define sleep_ms(x) usleep((x) * 1000)
#endif

#include <libusb.h>

#define TI_VID 0x0451
#define PID_84P 0xe008 /* TI-84 Plus, Plus C Silver Edition, Plus CE, TI-83 Premium CE */
#define PID_89T 0xe004 /* TI-89 Titanium */

enum { RPKT_BUF_REQ = 1, RPKT_BUF_ALLOC = 2, RPKT_DATA = 3, RPKT_DATA_LAST = 4, RPKT_ACK = 5 };
enum {
    VPKT_PING = 0x0001, VPKT_PARM_REQ = 0x0007, VPKT_PARM_DATA = 0x0008, VPKT_DIR_REQ = 0x0009,
    VPKT_VAR_HDR = 0x000A, VPKT_RTS = 0x000B, VPKT_VAR_REQ = 0x000C, VPKT_VAR_CNTS = 0x000D,
    VPKT_MODIF_VAR = 0x0010, VPKT_EXECUTE = 0x0011, VPKT_MODE_SET = 0x0012,
    VPKT_DATA_ACK = 0xAA00, VPKT_DELAY_ACK = 0xBB00, VPKT_EOT = 0xDD00, VPKT_ERROR = 0xEE00
};
/* Variable attributes (libticalcs: dusb_cmd.h, DUSB_AID_*) */
enum {
    AID_VAR_SIZE = 0x01, AID_VAR_TYPE = 0x02, AID_ARCHIVED = 0x03, AID_APPVAR = 0x05,
    AID_VAR_VERSION = 0x08, AID_DATATYPE = 0x11, AID_LOCKED = 0x41, AID_ACCESS = 0x42
};
enum {
    PID_PRODUCT_NAME = 0x0002, PID_OS_VERSION = 0x000B, PID_FREE_RAM = 0x000E,
    PID_FREE_FLASH = 0x0011, PID_SCREENSHOT = 0x0022, PID_BATTERY = 0x002D
};
/* The clock (libticalcs: dusb_cmd.h, DUSB_PID_CLK_*). The 89 Titanium and the older 84 Plus
   models count seconds since 1997-01-01 ("classic"); newer 84 Plus OSes take the date and
   time field by field ("new"). */
enum {
    PID_CLK_CLASSIC = 0x0023, PID_CLK_ON = 0x0024, PID_CLK_SECS_1997 = 0x0025,
    PID_CLK_DATE_FMT = 0x0027, PID_CLK_TIME_FMT = 0x0028, PID_CLK_NEW = 0x003A,
    PID_CLK_SECONDS = 0x003B, PID_CLK_MINUTES = 0x003C, PID_CLK_HOURS = 0x003D,
    PID_CLK_DAY = 0x003E, PID_CLK_MONTH = 0x003F, PID_CLK_YEAR = 0x0040
};
#define VPKT_PARM_SET 0x000E

#define RAW_MAX 1023
#define TIMEOUT_MS 5000

/* What differs between the models (libticalcs: dusb_vpkt.cc, dusb_cmd.cc, calc_89t.cc) */
typedef struct {
    const char *name;    /* --model */
    uint16_t pid;
    uint32_t raw_clamp;  /* The largest raw packet used, whatever the calculator allocates */
    int is_89t;          /* Keys high byte first with a pause, its own ZLP rule, 1 bpp screen */
} Model;

static const Model MODELS[] = {
    {"84ce", PID_84P, 1018, 0}, /* The CE allocates more than it handles */
    {"89t", PID_89T, RAW_MAX, 1},
};
#define N_MODELS ((int)(sizeof(MODELS) / sizeof(MODELS[0])))
#define MODEL_AUTO (-1)

typedef struct {
    const Model *m;
    uint32_t vtl_size;           /* The size of the virtual packet being sent (the ZLP rule) */
    libusb_context *ctx;
    libusb_device_handle *dev;
    unsigned char ep_in, ep_out;
    uint32_t maxlen;             /* The raw packet payload both sides agreed on */
    unsigned char inbuf[4096];   /* Bytes read from USB, not yet consumed */
    int in_len, in_pos;
    uint32_t progress_total;     /* Non-zero: vpkt_recv prints "PROGRESS <bytes> <total>" */
} Link;

static int usb_read_some(Link *l) {
    int got = 0;
    int r = libusb_bulk_transfer(l->dev, l->ep_in, l->inbuf, sizeof(l->inbuf), &got, TIMEOUT_MS);
    if (r != 0 && !(r == LIBUSB_ERROR_TIMEOUT && got > 0)) return -1;
    l->in_len = got;
    l->in_pos = 0;
    return 0;
}

static int usb_read(Link *l, unsigned char *out, int n) {
    while (n > 0) {
        if (l->in_pos >= l->in_len && usb_read_some(l)) return -1;
        int take = l->in_len - l->in_pos;
        if (take > n) take = n;
        memcpy(out, l->inbuf + l->in_pos, (size_t)take);
        l->in_pos += take;
        out += take;
        n -= take;
    }
    return 0;
}

/* One raw packet: 4 bytes of size (big endian), 1 byte of type, then the data */
static int raw_send(Link *l, int type, const unsigned char *data, uint32_t n) {
    unsigned char buf[5 + RAW_MAX];
    if (n > RAW_MAX) return -1;
    buf[0] = (unsigned char)(n >> 24);
    buf[1] = (unsigned char)(n >> 16);
    buf[2] = (unsigned char)(n >> 8);
    buf[3] = (unsigned char)n;
    buf[4] = (unsigned char)type;
    if (n) memcpy(buf + 5, data, n);
    int sent = 0;
    if (libusb_bulk_transfer(l->dev, l->ep_out, buf, (int)(5 + n), &sent, TIMEOUT_MS) != 0 ||
        sent != (int)(5 + n))
        return -1;
    /* The CE needs an empty packet after a final data packet that fills its USB packets
       exactly; the 89 Titanium too, but only in virtual packets over 1076 bytes
       (libticalcs: workaround_send) */
    if (type == RPKT_DATA_LAST && ((n + 5) % 64) == 0 && (!l->m->is_89t || l->vtl_size > 1076))
        libusb_bulk_transfer(l->dev, l->ep_out, buf, 0, &sent, TIMEOUT_MS);
    return 0;
}

/* The 89 Titanium follows a raw packet whose data is a multiple of 64 bytes with an empty USB
   packet (libticalcs: workaround_recv; ticables: the extra bulk read). usb_read needs no case
   for it: an empty read is just read again. */
static int raw_recv(Link *l, int *type, unsigned char *data, uint32_t *n) {
    unsigned char h[5];
    if (usb_read(l, h, 5)) return -1;
    uint32_t size = ((uint32_t)h[0] << 24) | ((uint32_t)h[1] << 16) | ((uint32_t)h[2] << 8) | h[3];
    if (size > RAW_MAX) return -1;
    *type = h[4];
    *n = size;
    return size ? usb_read(l, data, (int)size) : 0;
}

static int send_ack(Link *l) {
    static const unsigned char a[2] = {0xE0, 0x00};
    return raw_send(l, RPKT_ACK, a, 2);
}

/* The calculator's acknowledgement of a raw data packet. It may ask for a buffer size first. */
static int recv_ack(Link *l) {
    unsigned char d[RAW_MAX];
    uint32_t n;
    int type;
    if (raw_recv(l, &type, d, &n)) return -1;
    if (type == RPKT_BUF_REQ && n == 4) {
        if (raw_send(l, RPKT_BUF_ALLOC, d, 4)) return -1;
        if (raw_recv(l, &type, d, &n)) return -1;
    }
    return (type == RPKT_ACK) ? 0 : -1;
}

/* A virtual packet: 4 bytes of size, 2 of type, the data; cut into raw packets */
static int vpkt_send(Link *l, int vtype, const unsigned char *data, uint32_t n) {
    unsigned char raw[RAW_MAX];
    uint32_t first = l->maxlen - 6;
    raw[0] = (unsigned char)(n >> 24);
    raw[1] = (unsigned char)(n >> 16);
    raw[2] = (unsigned char)(n >> 8);
    raw[3] = (unsigned char)n;
    raw[4] = (unsigned char)(vtype >> 8);
    raw[5] = (unsigned char)vtype;
    l->vtl_size = n;
    if (n <= first) {
        if (n) memcpy(raw + 6, data, n);
        if (raw_send(l, RPKT_DATA_LAST, raw, n + 6) || recv_ack(l)) return -1;
        if (l->progress_total) printf("PROGRESS %lu %lu\n", (unsigned long)n, (unsigned long)l->progress_total);
        return 0;
    }
    memcpy(raw + 6, data, first);
    if (raw_send(l, RPKT_DATA, raw, l->maxlen) || recv_ack(l)) return -1;
    uint32_t off = first;
    while (off < n) {
        uint32_t take = n - off > l->maxlen ? l->maxlen : n - off;
        int last = (off + take == n);
        if (raw_send(l, last ? RPKT_DATA_LAST : RPKT_DATA, data + off, take) || recv_ack(l)) return -1;
        if (l->progress_total && ((off + take) / 8192 != off / 8192 || last))
            printf("PROGRESS %lu %lu\n", (unsigned long)(off + take), (unsigned long)l->progress_total);
        off += take;
    }
    return 0;
}

/* Receives one virtual packet into a malloc'd buffer (the caller frees it). A "delay" answer
   means: wait that long, the real answer follows. */
static int vpkt_recv(Link *l, int *vtype, unsigned char **out, uint32_t *n) {
    for (int tries = 0; tries < 8; tries++) {
        unsigned char raw[RAW_MAX];
        unsigned char *buf = NULL;
        uint32_t len = 0, cap = 0, rn;
        int rtype, first = 1;
        do {
            if (raw_recv(l, &rtype, raw, &rn)) {
                free(buf);
                return -1;
            }
            if (rtype != RPKT_DATA && rtype != RPKT_DATA_LAST) {
                free(buf);
                return -1;
            }
            const unsigned char *src = raw;
            if (first) {
                if (rn < 6) {
                    free(buf);
                    return -1;
                }
                *vtype = (raw[4] << 8) | raw[5];
                src = raw + 6;
                rn -= 6;
                first = 0;
            }
            if (len + rn > cap) {
                cap = (len + rn) * 2 + 1024;
                unsigned char *nb = realloc(buf, cap);
                if (!nb) {
                    free(buf);
                    return -1;
                }
                buf = nb;
            }
            memcpy(buf + len, src, rn);
            if (l->progress_total && (len + rn) / 16384 != len / 16384)
                printf("PROGRESS %lu %lu\n", (unsigned long)(len + rn),
                       (unsigned long)l->progress_total);
            len += rn;
            if (send_ack(l)) {
                free(buf);
                return -1;
            }
        } while (rtype != RPKT_DATA_LAST);
        if (*vtype == VPKT_DELAY_ACK) {
            // "Wait, the answer comes later": the next bulk read blocks until it does, so no
            // sleep here (TILP sleeps the hinted time, up to 400 ms, which made each key slow)
            free(buf);
            continue;
        }
        *out = buf;
        *n = len;
        return 0;
    }
    return -1;
}

static const Model *model_of(uint16_t pid, int want) {
    for (int i = 0; i < N_MODELS; i++)
        if (MODELS[i].pid == pid && (want == MODEL_AUTO || want == i)) return &MODELS[i];
    return NULL;
}

static int mode_set(Link *l);

static int link_open(Link *l, int want) {
    memset(l, 0, sizeof(*l));
    l->m = &MODELS[want == MODEL_AUTO ? 0 : want];
    if (libusb_init(&l->ctx)) {
        printf("ERR libusb_init failed\n");
        return 3;
    }
    libusb_device **list = NULL;
    ssize_t cnt = libusb_get_device_list(l->ctx, &list);
    int found = 0, rc = 2;
    for (ssize_t i = 0; i < cnt && !l->dev; i++) {
        struct libusb_device_descriptor d;
        if (libusb_get_device_descriptor(list[i], &d) || d.idVendor != TI_VID ||
            !model_of(d.idProduct, want))
            continue;
        found = 1;
        l->m = model_of(d.idProduct, want);
        int r = libusb_open(list[i], &l->dev);
        if (r) {
            l->dev = NULL;
            printf("ERR the calculator is on USB but cannot be opened: %s%s\n", libusb_error_name(r),
                   r == LIBUSB_ERROR_NOT_SUPPORTED ? " (it has no WinUSB driver: see the README)" : "");
            rc = 3;
        }
    }
    if (list) libusb_free_device_list(list, 1);
    if (!l->dev) {
        if (!found && want == MODEL_AUTO)
            printf("ERR no TI-84 Plus family calculator or TI-89 Titanium on USB\n");
        else if (!found && l->m->is_89t)
            printf("ERR no TI-89 Titanium on USB\n");
        else if (!found)
            printf("ERR no TI-84 Plus family calculator on USB\n");
        return rc;
    }
    libusb_set_configuration(l->dev, 1);
    if (libusb_claim_interface(l->dev, 0)) {
        printf("ERR cannot claim the USB interface (another program has it?)\n");
        return 3;
    }
    struct libusb_config_descriptor *cfg;
    if (libusb_get_active_config_descriptor(libusb_get_device(l->dev), &cfg) == 0) {
        const struct libusb_interface_descriptor *ifc = cfg->interface[0].altsetting;
        for (int i = 0; i < ifc->bNumEndpoints; i++) {
            unsigned char ep = ifc->endpoint[i].bEndpointAddress;
            if (ep & LIBUSB_ENDPOINT_IN) {
                if (!l->ep_in) l->ep_in = ep;
            } else if (!l->ep_out) {
                l->ep_out = ep;
            }
        }
        libusb_free_config_descriptor(cfg);
    }
    if (!l->ep_in) l->ep_in = 0x81;
    if (!l->ep_out) l->ep_out = 0x02;

    /* Leftovers of an earlier, interrupted conversation would be read as answers */
    {
        int got = 0;
        unsigned char junk[1024];
        while (libusb_bulk_transfer(l->dev, l->ep_in, junk, sizeof(junk), &got, 60) == 0 && got > 0) {
        }
    }

    return mode_set(l);
}

/* Agrees a raw packet size with the calculator: 0, or -1 if it didn't answer */
static int buf_size(Link *l, uint32_t want) {
    unsigned char b[4] = {(unsigned char)(want >> 24), (unsigned char)(want >> 16),
                          (unsigned char)(want >> 8), (unsigned char)want};
    unsigned char d[RAW_MAX];
    uint32_t n;
    int type;
    if (raw_send(l, RPKT_BUF_REQ, b, 4) || raw_recv(l, &type, d, &n) || type != RPKT_BUF_ALLOC || n != 4)
        return -1;
    l->maxlen = ((uint32_t)d[0] << 24) | ((uint32_t)d[1] << 16) | ((uint32_t)d[2] << 8) | d[3];
    if (l->maxlen > l->m->raw_clamp) l->maxlen = l->m->raw_clamp;
    if (l->maxlen > want) l->maxlen = want;
    if (l->maxlen < 16) l->maxlen = 250;
    return 0;
}

/* The handshake: agree a buffer size, then "normal mode" (libticalcs: dusb_cmd_s_mode_set;
   the 89 Titanium wants it again before each upload of an even size, calc_89t.cc: is_ready) */
static int mode_set(Link *l) {
    if (buf_size(l, 1024)) {
        printf("ERR the calculator did not answer (is it on, at the home screen?)\n");
        return 4;
    }
    static const unsigned char mode[10] = {0, 3, 0, 1, 0, 0, 0, 0, 0x07, 0xD0};
    unsigned char *ans = NULL;
    uint32_t n;
    int vt = 0;
    if (vpkt_send(l, VPKT_PING, mode, sizeof(mode)) || vpkt_recv(l, &vt, &ans, &n)) {
        printf("ERR the mode handshake failed\n");
        return 4;
    }
    free(ans);
    if (vt != VPKT_MODE_SET) {
        printf("ERR unexpected answer to the mode handshake (0x%04x)\n", vt);
        return 4;
    }
    return 0;
}

static void link_close(Link *l) {
    if (l->dev) {
        libusb_release_interface(l->dev, 0);
        libusb_close(l->dev);
    }
    if (l->ctx) libusb_exit(l->ctx);
}

/* Asks for parameters; the answer's data: count(2), then per parameter id(2), ok(1, 0 = ok),
   size(2), data */
static int param_request(Link *l, const uint16_t *pids, int np, unsigned char **out, uint32_t *n) {
    unsigned char req[2 + 2 * 16];
    if (np > 16) return 1;
    req[0] = 0;
    req[1] = (unsigned char)np;
    for (int i = 0; i < np; i++) {
        req[2 + 2 * i] = (unsigned char)(pids[i] >> 8);
        req[3 + 2 * i] = (unsigned char)pids[i];
    }
    int vt = 0;
    if (vpkt_send(l, VPKT_PARM_REQ, req, (uint32_t)(2 + 2 * np)) || vpkt_recv(l, &vt, out, n)) return 4;
    if (vt != VPKT_PARM_DATA) {
        free(*out);
        *out = NULL;
        return 4;
    }
    return 0;
}

static int do_info(Link *l) {
    static const uint16_t pids[] = {PID_PRODUCT_NAME, PID_OS_VERSION, PID_FREE_RAM, PID_FREE_FLASH};
    unsigned char *d = NULL;
    uint32_t n = 0;
    if (param_request(l, pids, 4, &d, &n)) {
        printf("ERR device info: no answer\n");
        return 4;
    }
    uint32_t p = 2;
    while (p + 5 <= n) {
        unsigned id = (d[p] << 8) | d[p + 1];
        int ok = d[p + 2] == 0;
        p += 3;
        if (!ok) continue;
        unsigned sz = (d[p] << 8) | d[p + 1];
        p += 2;
        if (p + sz > n) break;
        const unsigned char *v = d + p;
        if (id == PID_PRODUCT_NAME) {
            printf("INFO name=");
            for (unsigned i = 0; i < sz && v[i]; i++) putchar(v[i] == ' ' ? '_' : v[i]);
            printf("\n");
        } else if (id == PID_OS_VERSION && sz >= 4 && l->m->is_89t) {
            printf("INFO os=%u.%02u\n", v[1], v[2]); /* As calc_89t.cc reads it */
        } else if (id == PID_OS_VERSION && sz >= 4) {
            printf("INFO os=%u.%u.%u\n", v[1], v[2], v[3]); /* As calc_84p.cc reads it (byte 0 isn't part of it) */
        } else if ((id == PID_FREE_RAM || id == PID_FREE_FLASH) && sz >= 8) {
            unsigned long long x = 0;
            for (int i = 0; i < 8; i++) x = (x << 8) | v[i];
            printf("INFO %s=%llu\n", id == PID_FREE_RAM ? "ram_free" : "storage_free", x);
        }
        p += sz;
    }
    free(d);
    printf("OK\n");
    return 0;
}

static int do_shot(Link *l, const char *out) {
    static const uint16_t pid[] = {PID_SCREENSHOT};
    unsigned char *d = NULL;
    uint32_t n = 0;
    if (param_request(l, pid, 1, &d, &n)) {
        printf("ERR screenshot: no answer\n");
        return 4;
    }
    if (n < 7 || ((d[2] << 8) | d[3]) != PID_SCREENSHOT || d[4] != 0) {
        printf("ERR screenshot: refused\n");
        free(d);
        return 4;
    }
    const unsigned char *px = d + 7;
    uint32_t size = n - 7;
    unsigned w, h;
    unsigned char *rgb;
    if (size == 320 * 240 * 2) { /* The CE: RGB565, low byte first */
        w = 320;
        h = 240;
        rgb = malloc(w * h * 3);
        if (!rgb) {
            free(d);
            return 6;
        }
        for (unsigned k = 0; k < w * h; k++) {
            unsigned v = px[2 * k] | ((unsigned)px[2 * k + 1] << 8);
            unsigned r5 = (v >> 11) & 31, g6 = (v >> 5) & 63, b5 = v & 31;
            rgb[3 * k] = (unsigned char)((r5 << 3) | (r5 >> 2));
            rgb[3 * k + 1] = (unsigned char)((g6 << 2) | (g6 >> 4));
            rgb[3 * k + 2] = (unsigned char)((b5 << 3) | (b5 >> 2));
        }
    } else if (size == 96 * 64 / 8) { /* The monochrome 84 Plus: 1 bit a pixel, 1 = dark */
        w = 96;
        h = 64;
        rgb = malloc(w * h * 3);
        if (!rgb) {
            free(d);
            return 6;
        }
        for (unsigned k = 0; k < w * h; k++) {
            unsigned char c = (px[k / 8] & (0x80 >> (k & 7))) ? 0x20 : 0xC8;
            rgb[3 * k] = rgb[3 * k + 1] = rgb[3 * k + 2] = c;
        }
    } else if (size == 240 * 128 / 8) {
        /* The 89 Titanium: 1 bit a pixel, 1 = dark, rows of 240 pixels (30 bytes) of which the
           LCD shows the top-left 160 x 100 (calc_89t.cc: recv_screen). Dark on the LCD's
           grey-green. */
        w = 160;
        h = 100;
        rgb = malloc(w * h * 3);
        if (!rgb) {
            free(d);
            return 6;
        }
        for (unsigned y = 0; y < h; y++) {
            for (unsigned x = 0; x < w; x++) {
                int on = (px[y * 30 + x / 8] & (0x80 >> (x & 7))) != 0;
                unsigned char *o = rgb + 3 * (y * w + x);
                o[0] = on ? 0x20 : 0xC8;
                o[1] = on ? 0x24 : 0xD0;
                o[2] = on ? 0x20 : 0xB8;
            }
        }
    } else {
        printf("ERR screenshot: %u bytes is a format this tool doesn't read\n", (unsigned)size);
        free(d);
        return 4;
    }
    FILE *f = fopen(out, "wb");
    if (!f) {
        printf("ERR cannot write %s\n", out);
        free(rgb);
        free(d);
        return 6;
    }
    fprintf(f, "P6\n%u %u\n255\n", w, h);
    fwrite(rgb, 1, (size_t)w * h * 3, f);
    fclose(f);
    printf("OK shot %ux%u %s\n", w, h, out);
    free(rgb);
    free(d);
    return 0;
}

/* One key press: the remote "execute key" command, then the calculator's two answers */
static int do_key(Link *l, unsigned long code) {
    unsigned char e[5] = {0, 0, 0x03, 0, 0};
    if (l->m->is_89t) { /* Always high byte first, and a pause between two keys (calc_89t.cc) */
        sleep_ms(25);
        e[3] = (unsigned char)(code >> 8);
        e[4] = (unsigned char)code;
    } else if ((code >> 8) == 0) { /* A one-byte key: high byte first (the eZ80 OS needs that) */
        e[3] = 0;
        e[4] = (unsigned char)code;
    } else { /* A two-byte key: the extension byte first */
        e[3] = (unsigned char)code;
        e[4] = (unsigned char)(code >> 8);
    }
    unsigned char *a = NULL;
    uint32_t n = 0;
    int vt = 0;
    if (vpkt_send(l, VPKT_EXECUTE, e, 5)) return 4;
    /* A "delay" answer is taken by vpkt_recv; then comes the data acknowledgement */
    if (vpkt_recv(l, &vt, &a, &n)) return 4;
    free(a);
    if (vt == VPKT_ERROR) return 4;
    return 0;
}

/* ---- Variables: list, download, upload, delete (libticalcs: dusb_cmd.cc, calc_84p.cc,
   calc_89t.cc). Names and folders travel as hex on our command lines: a calculator's names
   are its own character set, not text the PC can print. ---- */

typedef struct {
    uint16_t id;
    int ok;
    uint16_t size;
    const unsigned char *data;
} Attr;

static void put_hex(const unsigned char *s, unsigned n) {
    if (!n) printf("-");
    for (unsigned i = 0; i < n; i++) printf("%02x", s[i]);
}

/* "414243" -> "ABC" (up to cap - 1 bytes, then a 0); "-" is the empty name. -1 if not hex. */
static int from_hex(const char *hex, unsigned char *out, unsigned cap) {
    unsigned n = 0;
    if (!strcmp(hex, "-")) {
        out[0] = 0;
        return 0;
    }
    for (const char *p = hex; p[0]; p += 2) {
        unsigned v;
        if (!p[1] || n + 1 >= cap || sscanf(p, "%2x", &v) != 1) return -1;
        if (v == 0) return -1; /* A name never has a 0 inside: the packets end names with one */
        out[n++] = (unsigned char)v;
    }
    out[n] = 0;
    return (int)n;
}

/* A var header packet: folder, name, then the attributes asked for. 0 ok, -1 malformed. */
static int parse_var_header(const unsigned char *d, uint32_t n, unsigned char *folder,
                            unsigned *flen, unsigned char *name, unsigned *nlen, Attr *a,
                            int max_attr, int *nattr) {
    uint32_t j = 0;
    unsigned len;
    for (int part = 0; part < 2; part++) {
        unsigned char *dst = part ? name : folder;
        if (j >= n) return -1;
        len = d[j++];
        if (len > 39 || (len && j + len + 1 > n)) return -1;
        memcpy(dst, d + j, len);
        dst[len] = 0;
        if (len) j += len + 1;
        *(part ? nlen : flen) = len;
    }
    if (j + 2 > n) return -1;
    int na = (d[j] << 8) | d[j + 1];
    j += 2;
    *nattr = 0;
    for (int i = 0; i < na; i++) {
        if (j + 3 > n) return -1;
        Attr t = {(uint16_t)((d[j] << 8) | d[j + 1]), d[j + 2] == 0, 0, NULL};
        j += 3;
        if (t.ok) {
            if (j + 2 > n) return -1;
            t.size = (uint16_t)((d[j] << 8) | d[j + 1]);
            j += 2;
            if (j + t.size > n) return -1;
            t.data = d + j;
            j += t.size;
        }
        if (*nattr < max_attr) a[(*nattr)++] = t;
    }
    return 0;
}

static const Attr *find_attr(const Attr *a, int n, uint16_t id, uint16_t min_size) {
    for (int i = 0; i < n; i++)
        if (a[i].id == id && a[i].ok && a[i].size >= min_size) return &a[i];
    return NULL;
}

static uint32_t be32(const unsigned char *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

/* An answer that must be the data acknowledgement; prints the calculator's error otherwise */
static int expect_ack(Link *l, const char *what) {
    unsigned char *a = NULL;
    uint32_t n = 0;
    int vt = 0;
    if (vpkt_recv(l, &vt, &a, &n)) {
        printf("ERR %s: no answer\n", what);
        return 4;
    }
    if (vt != VPKT_DATA_ACK) {
        printf("ERR %s: the calculator said no (0x%04x, code 0x%04x)\n", what, vt,
               n >= 2 ? (unsigned)((a[0] << 8) | a[1]) : 0u);
        free(a);
        return 4;
    }
    free(a);
    return 0;
}

/* Lists the variables, programs and apps:
   "ITEM type=05 size=123 arch=1 locked=0 folder=HEX name=HEX" each */
static int do_ls(Link *l) {
    static const uint16_t aids84[] = {AID_VAR_SIZE, AID_VAR_TYPE, AID_ARCHIVED};
    static const uint16_t aids89[] = {AID_VAR_TYPE, AID_ARCHIVED, AID_APPVAR,
                                      AID_VAR_SIZE, AID_LOCKED, AID_ACCESS};
    const uint16_t *aids = l->m->is_89t ? aids89 : aids84;
    const int naids = l->m->is_89t ? 6 : 3;
    unsigned char req[4 + 2 * 6 + 7];
    uint32_t j = 0;
    req[j++] = 0;
    req[j++] = 0;
    req[j++] = 0;
    req[j++] = (unsigned char)naids;
    for (int i = 0; i < naids; i++) {
        req[j++] = (unsigned char)(aids[i] >> 8);
        req[j++] = (unsigned char)aids[i];
    }
    static const unsigned char tail[7] = {0, 1, 0, 1, 0, 1, 1};
    memcpy(req + j, tail, sizeof(tail));
    j += sizeof(tail);
    if (vpkt_send(l, VPKT_DIR_REQ, req, j)) {
        printf("ERR ls: no answer\n");
        return 4;
    }
    int count = 0;
    for (;;) {
        unsigned char *d = NULL;
        uint32_t n = 0;
        int vt = 0;
        if (vpkt_recv(l, &vt, &d, &n)) {
            printf("ERR ls: no answer after %d\n", count);
            return 4;
        }
        if (vt == VPKT_EOT) {
            free(d);
            break;
        }
        if (vt != VPKT_VAR_HDR) {
            printf("ERR ls: unexpected answer 0x%04x\n", vt);
            free(d);
            return 4;
        }
        unsigned char folder[40], name[40];
        unsigned flen, nlen;
        Attr a[8];
        int na;
        if (parse_var_header(d, n, folder, &flen, name, &nlen, a, 8, &na)) {
            printf("ERR ls: a listing entry could not be read\n");
            free(d);
            return 4;
        }
        const Attr *ty = find_attr(a, na, AID_VAR_TYPE, 4);
        const Attr *sz = find_attr(a, na, AID_VAR_SIZE, 4);
        const Attr *ar = find_attr(a, na, AID_ARCHIVED, 1);
        const Attr *lk = find_attr(a, na, AID_LOCKED, 1);
        printf("ITEM type=%02x size=%lu arch=%d locked=%d folder=", ty ? ty->data[3] : 0xff,
               sz ? (unsigned long)be32(sz->data) : 0ul, ar ? ar->data[0] != 0 : 0,
               lk ? lk->data[0] != 0 : 0);
        put_hex(folder, flen);
        printf(" name=");
        put_hex(name, nlen);
        printf("\n");
        free(d);
        count++;
    }
    printf("OK %d item(s)\n", count);
    return 0;
}

/* "get TYPE FOLDERHEX NAMEHEX SIZE LOCAL": the variable's data into LOCAL as it is (no TI file
   header: the Python side writes that). Prints "OK got size=N arch=A version=V". */
static int do_get(Link *l, char *arg) {
    char *tok[5];
    for (int i = 0; i < 4; i++) {
        tok[i] = strtok(i ? NULL : arg, " ");
        if (!tok[i]) {
            printf("ERR usage: get TYPE FOLDERHEX NAMEHEX SIZE LOCAL\n");
            return 1;
        }
    }
    tok[4] = strtok(NULL, ""); /* The path, spaces and all */
    unsigned char folder[40], name[40];
    int flen = from_hex(tok[1], folder, sizeof(folder)), nlen = from_hex(tok[2], name, sizeof(name));
    if (!tok[4] || flen < 0 || nlen <= 0) {
        printf("ERR usage: get TYPE FOLDERHEX NAMEHEX SIZE LOCAL\n");
        return 1;
    }
    unsigned type = (unsigned)strtoul(tok[0], NULL, 16);
    static const uint16_t aids84[] = {AID_ARCHIVED, AID_VAR_VERSION, AID_VAR_SIZE};
    static const uint16_t aids89[] = {AID_ARCHIVED, AID_VAR_VERSION, AID_LOCKED};
    const uint16_t *aids = l->m->is_89t ? aids89 : aids84;
    unsigned char req[128];
    uint32_t j = 0;
    req[j++] = (unsigned char)flen;
    if (flen) {
        memcpy(req + j, folder, (size_t)flen + 1);
        j += (uint32_t)flen + 1;
    }
    req[j++] = (unsigned char)nlen;
    memcpy(req + j, name, (size_t)nlen + 1);
    j += (uint32_t)nlen + 1;
    static const unsigned char any[5] = {0x01, 0xFF, 0xFF, 0xFF, 0xFF};
    memcpy(req + j, any, 5);
    j += 5;
    req[j++] = 0;
    req[j++] = 3;
    for (int i = 0; i < 3; i++) {
        req[j++] = (unsigned char)(aids[i] >> 8);
        req[j++] = (unsigned char)aids[i];
    }
    /* One attribute: the data type (0xF0 0x07 on the 84 family, 0xF0 0x0C on the 89) */
    req[j++] = 0;
    req[j++] = 1;
    req[j++] = 0;
    req[j++] = AID_DATATYPE;
    req[j++] = 0;
    req[j++] = 4;
    req[j++] = 0xF0;
    req[j++] = l->m->is_89t ? 0x0C : 0x07;
    req[j++] = 0x00;
    req[j++] = (unsigned char)type;
    req[j++] = 0;
    req[j++] = 0;
    if (vpkt_send(l, VPKT_VAR_REQ, req, j)) {
        printf("ERR get: no answer\n");
        return 4;
    }
    unsigned char *d = NULL;
    uint32_t n = 0;
    int vt = 0;
    if (vpkt_recv(l, &vt, &d, &n)) {
        printf("ERR get: no answer\n");
        return 4;
    }
    if (vt != VPKT_VAR_HDR) {
        printf("ERR get: the calculator refused (0x%04x, code 0x%04x)\n", vt,
               n >= 2 ? (unsigned)((d[0] << 8) | d[1]) : 0u);
        free(d);
        return 4;
    }
    unsigned char f2[40], n2[40];
    unsigned f2l, n2l;
    Attr a[8];
    int na = 0;
    int arch = 0;
    unsigned version = 0;
    if (parse_var_header(d, n, f2, &f2l, n2, &n2l, a, 8, &na) == 0) {
        const Attr *ar = find_attr(a, na, AID_ARCHIVED, 1);
        const Attr *ve = find_attr(a, na, AID_VAR_VERSION, 4);
        arch = ar ? ar->data[0] != 0 : 0;
        version = ve ? ve->data[3] : 0;
    }
    free(d);
    d = NULL;
    l->progress_total = (uint32_t)strtoul(tok[3], NULL, 10);
    if (!l->progress_total) l->progress_total = 1;
    int r = vpkt_recv(l, &vt, &d, &n);
    l->progress_total = 0;
    if (r) {
        printf("ERR get: the data didn't come\n");
        return 4;
    }
    if (vt != VPKT_VAR_CNTS) {
        printf("ERR get: unexpected answer 0x%04x\n", vt);
        free(d);
        return 4;
    }
    FILE *f = fopen(tok[4], "wb");
    if (!f || fwrite(d, 1, n, f) != n) {
        if (f) fclose(f);
        printf("ERR cannot write %s\n", tok[4]);
        free(d);
        return 6;
    }
    fclose(f);
    free(d);
    printf("OK got size=%lu arch=%d version=%u\n", (unsigned long)n, arch, version);
    return 0;
}

/* The VAR_TYPE header byte the 84 family wants on an upload: 0x0F on the CE models, 0x0B on
   the other USB ones (calc_84p.cc: get_var_type_attr_header_byte) */
static int is_ce(Link *l) {
    static const uint16_t pid[] = {PID_PRODUCT_NAME};
    unsigned char *d = NULL;
    uint32_t n = 0;
    int ce = 1; /* What this tool is tested on */
    if (param_request(l, pid, 1, &d, &n) == 0) {
        if (n > 7 && d[4] == 0) {
            ce = 0;
            for (uint32_t i = 7; i + 1 < n; i++)
                if (d[i] == 'C' && d[i + 1] == 'E') ce = 1;
        }
        free(d);
    }
    return ce;
}

/* Sends one variable (libticalcs: calc_84p.cc and calc_89t.cc, send_var): the request to send
   with the variable's attributes, its data, the end. folder is "" on the 84 family. A
   variable of the same name on the calculator is replaced. Prints PROGRESS lines. */
static int send_var(Link *l, const unsigned char *folder, unsigned flen, const unsigned char *name,
                    unsigned nlen, unsigned type, int arch, unsigned version,
                    const unsigned char *data, uint32_t size) {
    if (size == 0 || size > 65535 || nlen == 0 || nlen > 39 || flen > 39) {
        printf("ERR the variable's size (%lu bytes) or name can't be right\n", (unsigned long)size);
        return 6;
    }
    int t89 = l->m->is_89t;
    /* The 89 Titanium: "normal mode" again before an even size; an odd size is sent in small
       even raw packets agreed after the request (calc_89t.cc, as TI's own software does) */
    if (t89 && !(size & 1) && mode_set(l)) return 4;
    unsigned char req[160];
    uint32_t j = 0;
    req[j++] = (unsigned char)flen;
    if (flen) {
        memcpy(req + j, folder, flen);
        req[j + flen] = 0;
        j += flen + 1;
    }
    req[j++] = (unsigned char)nlen;
    memcpy(req + j, name, nlen);
    req[j + nlen] = 0;
    j += nlen + 1;
    req[j++] = (unsigned char)(size >> 24);
    req[j++] = (unsigned char)(size >> 16);
    req[j++] = (unsigned char)(size >> 8);
    req[j++] = (unsigned char)size;
    req[j++] = 0x01; /* "Silent" */
    req[j++] = 0;
    req[j++] = (unsigned char)(t89 ? 4 : 3);
    const unsigned char hdr = (unsigned char)(t89 ? 0x0C : (is_ce(l) ? 0x0F : 0x0B));
    const unsigned char attrs[] = {
        0, AID_VAR_TYPE, 0, 4, 0xF0, hdr, 0, (unsigned char)type,
        0, AID_ARCHIVED, 0, 1, (unsigned char)(arch ? 1 : 0),
        0, AID_VAR_VERSION, 0, 4, 0, 0, 0, (unsigned char)(t89 ? 0 : version),
        0, AID_LOCKED, 0, 1, 0}; /* The 89 only: the last attribute */
    uint32_t alen = sizeof(attrs) - (t89 ? 0 : 5);
    memcpy(req + j, attrs, alen);
    j += alen;
    if (vpkt_send(l, VPKT_RTS, req, j)) {
        printf("ERR send: no answer\n");
        return 4;
    }
    if (expect_ack(l, "send (no room, or a name the calculator doesn't take?)")) return 4;
    if (t89 && (size & 1)) {
        uint32_t pkt = (size / 10) & ~1u;
        if (pkt < 0x3A) pkt = 0x3A;
        if (pkt > 1022) pkt = 1022;
        if (buf_size(l, pkt)) {
            printf("ERR send: the calculator didn't agree a packet size\n");
            return 4;
        }
    }
    l->progress_total = size;
    int r = vpkt_send(l, VPKT_VAR_CNTS, data, size);
    l->progress_total = 0;
    if (r) {
        printf("ERR send: the data didn't go\n");
        return 4;
    }
    if (expect_ack(l, "send")) return 4;
    if (vpkt_send(l, VPKT_EOT, NULL, 0)) {
        printf("ERR send: no answer at the end\n");
        return 4;
    }
    sleep_ms(50); /* libticalcs: "needed" */
    if (t89 && (size & 1) && mode_set(l)) return 4; /* Back to full-size packets */
    return 0;
}

/* "put TYPE ARCH VERSION NAMEHEX LOCAL": LOCAL holds the variable's data (from a TI file, as
   the Python side reads it). The 84 family only (the 89 needs a folder: use send). */
static int do_put(Link *l, char *arg) {
    if (l->m->is_89t) {
        printf("ERR put is for the 84 family: send a .89? file with send\n");
        return 1;
    }
    char *tok[5];
    for (int i = 0; i < 4; i++) {
        tok[i] = strtok(i ? NULL : arg, " ");
        if (!tok[i]) {
            printf("ERR usage: put TYPE ARCH VERSION NAMEHEX LOCAL\n");
            return 1;
        }
    }
    tok[4] = strtok(NULL, "");
    unsigned char name[40];
    int nlen = from_hex(tok[3], name, sizeof(name));
    if (!tok[4] || nlen <= 0) {
        printf("ERR usage: put TYPE ARCH VERSION NAMEHEX LOCAL\n");
        return 1;
    }
    FILE *f = fopen(tok[4], "rb");
    if (!f) {
        printf("ERR cannot open local file %s\n", tok[4]);
        return 6;
    }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size <= 0 || size > 65535) {
        fclose(f);
        printf("ERR the variable's size (%ld bytes) can't be right\n", size);
        return 6;
    }
    unsigned char *data = malloc((size_t)size);
    if (!data || fread(data, 1, (size_t)size, f) != (size_t)size) {
        fclose(f);
        free(data);
        printf("ERR cannot read %s\n", tok[4]);
        return 6;
    }
    fclose(f);
    int r = send_var(l, (const unsigned char *)"", 0, name, (unsigned)nlen,
                     (unsigned)strtoul(tok[0], NULL, 16), atoi(tok[1]),
                     (unsigned)strtoul(tok[2], NULL, 10), data, (uint32_t)size);
    if (!r) printf("OK sent %ld bytes\n", size);
    free(data);
    return r;
}

/* ---- TI files (libtifiles: files8x.cc, files9x.cc) ---- */

static uint16_t le16(const unsigned char *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Appends s (UTF-8) to out; 0 if it fits */
static int put_str(unsigned char *out, unsigned *n, unsigned cap, const char *s) {
    size_t k = strlen(s);
    if (*n + k >= cap) return -1;
    memcpy(out + *n, s, k);
    *n += (unsigned)k;
    return 0;
}

/* A subscript digit in UTF-8: U+2080 + d */
static int put_sub(unsigned char *out, unsigned *n, unsigned cap, int d) {
    char s[4] = {(char)0xE2, (char)0x82, (char)(0x80 + d), 0};
    return put_str(out, n, cap, s);
}

/* The 8 bytes of a .8x? file's name -> the name the link wants ("L₁", "Str1", "[A]", "θ" as
   UTF-8); calc_files.py: detokenize_name_84 does the same */
static int name84(const unsigned char *raw8, unsigned char *out, unsigned cap) {
    unsigned char raw[8];
    unsigned len = 0, n = 0;
    static const unsigned char toks[] = {0x3C, 0x5C, 0x5D, 0x5E, 0x60, 0x61, 0xAA};
    int tok = memchr(toks, raw8[0], sizeof(toks)) != NULL;
    memcpy(raw, raw8, 8);
    len = 8;
    while (len > (tok ? 2u : 0u) && raw[len - 1] == 0) len--;
    if (len == 2 && tok) {
        unsigned a = raw[0], b = raw[1];
        int un = b == 9 ? 0 : (int)b + 1;
        char s[16];
        if (a == 0x5C && b <= 9) {
            snprintf(s, sizeof(s), "[%c]", 'A' + b);
            return put_str(out, &n, cap, s) ? -1 : (int)n;
        }
        if (a == 0x5D && b <= 5) return put_str(out, &n, cap, "L") || put_sub(out, &n, cap, b + 1) ? -1 : (int)n;
        if (a == 0x5E && b >= 0x10 && b <= 0x19)
            return put_str(out, &n, cap, "Y") || put_sub(out, &n, cap, (b - 0x10) == 9 ? 0 : b - 0x10 + 1) ? -1 : (int)n;
        if (a == 0x5E && b >= 0x20 && b <= 0x2B)
            return put_str(out, &n, cap, (b - 0x20) & 1 ? "Y" : "X") ||
                           put_sub(out, &n, cap, (b - 0x20) / 2 + 1) || put_str(out, &n, cap, "\xE1\xB4\x9B")
                       ? -1 : (int)n;
        if (a == 0x5E && b >= 0x40 && b <= 0x45)
            return put_str(out, &n, cap, "r") || put_sub(out, &n, cap, b - 0x40 + 1) ? -1 : (int)n;
        if (a == 0x5E && b >= 0x80 && b <= 0x82) {
            snprintf(s, sizeof(s), "%c", "uvw"[b - 0x80]);
            return put_str(out, &n, cap, s) ? -1 : (int)n;
        }
        const char *word = a == 0x60 ? "Pic" : a == 0x61 ? "GDB" : a == 0xAA ? "Str" : a == 0x3C ? "Image" : NULL;
        if (word && b <= 9) {
            snprintf(s, sizeof(s), "%s%d", word, un);
            return put_str(out, &n, cap, s) ? -1 : (int)n;
        }
    }
    unsigned i = raw[0] == 0x5D ? 1 : 0; /* A named list: its letters */
    for (; i < len; i++) {
        if (raw[i] == '[') {
            if (put_str(out, &n, cap, "\xCE\xB8")) return -1; /* theta */
        } else if (raw[i] >= 0x20 && raw[i] < 0x7F) {
            if (n + 1 >= cap) return -1;
            out[n++] = raw[i];
        } else {
            return -1;
        }
    }
    return n ? (int)n : -1;
}

/* Reads a whole local file (up to 1 MB) into a malloc'd buffer */
static unsigned char *read_file(const char *path, long *size) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    *size = ftell(f);
    fseek(f, 0, SEEK_SET);
    unsigned char *b = NULL;
    if (*size > 0 && *size <= (1L << 20)) {
        b = malloc((size_t)*size);
        if (b && fread(b, 1, (size_t)*size, f) != (size_t)*size) {
            free(b);
            b = NULL;
        }
    }
    fclose(f);
    return b;
}

static int sent_line(int t89, const unsigned char *folder, unsigned flen, const unsigned char *name,
                     unsigned nlen, unsigned type, uint32_t size) {
    printf("SENT type=%02x size=%lu folder=", type, (unsigned long)size);
    put_hex(folder, t89 ? flen : 0);
    printf(" name=");
    put_hex(name, nlen);
    printf("\n");
    return 0;
}

/* "send FILE": every variable in a TI file (.8xp .8xv .8xl ... for the 84 family; .89p
   .89e ... for the 89 Titanium). Refuses files for the other calculator, apps, OSes and
   backups. A variable of the same name is replaced: the caller asks first. */
static int do_send(Link *l, const char *path) {
    long fsize = 0;
    unsigned char *b = read_file(path, &fsize);
    if (!b) {
        printf("ERR cannot read %s\n", path);
        return 6;
    }
    int t89 = l->m->is_89t, r = 0, count = 0;
    const char *other = t89 ? "the TI-84 Plus family" : "the TI-89 Titanium";
    if (fsize >= 8 && !memcmp(b, "**TIFL**", 8)) {
        printf("ERR this is an app or an OS (a flash file): those can't be sent here\n");
        r = 1;
    } else if (fsize >= 8 && !memcmp(b, "**TI83F*", 8)) {
        if (t89) {
            printf("ERR this is a TI-84 Plus file: send it to %s\n", other);
            r = 1;
        } else if (fsize < 57) {
            printf("ERR the file is cut short\n");
            r = 6;
        } else {
            uint32_t blen = le16(b + 53), sum = 0;
            if (55 + blen + 2 > (uint32_t)fsize) {
                printf("ERR the file is cut short\n");
                r = 6;
            }
            for (uint32_t i = 0; !r && i < blen; i++) sum += b[55 + i];
            if (!r && (sum & 0xFFFF) != le16(b + 55 + blen)) {
                printf("ERR the file's checksum is wrong (damaged file?)\n");
                r = 6;
            }
            const unsigned char *body = b + 55;
            uint32_t p = 0;
            while (!r && p + 4 <= blen) {
                unsigned hlen = le16(body + p), dlen = le16(body + p + 2);
                if ((hlen != 0x0B && hlen != 0x0D) || p + 2 + hlen + 2 + dlen > blen) {
                    printf("ERR a variable in the file can't be read\n");
                    r = 6;
                    break;
                }
                unsigned type = body[p + 4];
                unsigned version = hlen == 0x0D ? body[p + 13] : 0;
                int arch = hlen == 0x0D ? (body[p + 14] & 0x80) != 0 : 0;
                unsigned char name[40];
                int nlen = name84(body + p + 5, name, sizeof(name));
                const unsigned char *data = body + p + 2 + hlen + 2;
                p += 2 + hlen + 2 + dlen;
                if (type == 0x13 || type == 0x23 || type == 0x24 || type == 0x25 || type == 0x26 ||
                    type == 0x27) {
                    printf("ERR backups, apps, certificates and OS files can't be sent here\n");
                    r = 1;
                } else if (nlen <= 0) {
                    printf("ERR a name in the file can't be read\n");
                    r = 6;
                } else if (!(r = send_var(l, (const unsigned char *)"", 0, name, (unsigned)nlen,
                                          type, arch, version, data, dlen))) {
                    sent_line(0, NULL, 0, name, (unsigned)nlen, type, dlen);
                    count++;
                }
            }
        }
    } else if (fsize >= 8 && (!memcmp(b, "**TI89**", 8) || !memcmp(b, "**TI92P*", 8))) {
        if (!t89) {
            printf("ERR this is a TI-89 file: send it to %s\n", other);
            r = 1;
        } else if (fsize < 0x3C) {
            printf("ERR the file is cut short\n");
            r = 6;
        } else {
            unsigned char folder[9] = {0};
            memcpy(folder, b + 0x0A, 8);
            unsigned n = le16(b + 0x3A);
            uint32_t t = 0x3C;
            for (unsigned i = 0; !r && i < n; i++, t += 16) {
                if (t + 16 + 4 > (uint32_t)fsize) {
                    printf("ERR the file is cut short\n");
                    r = 6;
                    break;
                }
                uint32_t off = le32(b + t), next = le32(b + t + 16);
                unsigned char name[9] = {0};
                memcpy(name, b + t + 4, 8);
                unsigned type = b[t + 12], attr = b[t + 13];
                if (type == 0x1F) { /* A folder: the variables after it are in it */
                    memcpy(folder, name, 9);
                    continue;
                }
                if (off + 6 > next || next > (uint32_t)fsize) {
                    printf("ERR a variable in the file can't be read\n");
                    r = 6;
                    break;
                }
                uint32_t size = next - off - 6, sum = 0;
                const unsigned char *data = b + off + 4;
                for (uint32_t k = 0; k < size; k++) sum += data[k];
                if ((sum & 0xFFFF) != le16(data + size)) {
                    printf("ERR the file's checksum is wrong (damaged file?)\n");
                    r = 6;
                    break;
                }
                if (type == 0x1D || type == 0x23 || type == 0x24 || type == 0x18) {
                    printf("ERR backups, apps and OS files can't be sent here\n");
                    r = 1;
                    break;
                }
                unsigned flen = (unsigned)strlen((const char *)folder), nlen = (unsigned)strlen((const char *)name);
                const unsigned char *fold = flen ? folder : (const unsigned char *)"main";
                if (!flen) flen = 4;
                if (!(r = send_var(l, fold, flen, name, nlen, type, attr == 2 || attr == 3, 0, data, size))) {
                    sent_line(1, fold, flen, name, nlen, type, size);
                    count++;
                }
            }
        }
    } else if (fsize >= 8 && !memcmp(b, "**TI", 4)) {
        printf("ERR a file for another calculator (%.8s): this one takes %s files\n", (const char *)b,
               t89 ? ".89?" : ".8x?");
        r = 1;
    } else {
        printf("ERR not a TI file (%s)\n", path);
        r = 1;
    }
    free(b);
    if (!r && count == 0) {
        printf("ERR no variable in the file\n");
        r = 6;
    }
    if (!r) printf("OK sent %d variable(s)\n", count);
    return r;
}

/* "rm TYPE NAMEHEX [FOLDERHEX]": deletes a variable (the 89 needs its folder) */
static int do_rm(Link *l, char *arg) {
    char *t = strtok(arg, " "), *h = strtok(NULL, " "), *fh = strtok(NULL, " ");
    unsigned char name[40], folder[40];
    int nlen = h ? from_hex(h, name, sizeof(name)) : -1;
    int flen = fh ? from_hex(fh, folder, sizeof(folder)) : 0;
    if (!t || nlen <= 0 || flen < 0 || (l->m->is_89t && flen <= 0)) {
        printf("ERR usage: rm TYPE NAMEHEX%s\n", l->m->is_89t ? " FOLDERHEX" : "");
        return 1;
    }
    unsigned char req[128];
    uint32_t j = 0;
    req[j++] = (unsigned char)flen;
    if (flen) {
        memcpy(req + j, folder, (size_t)flen + 1);
        j += (uint32_t)flen + 1;
    }
    req[j++] = (unsigned char)nlen;
    memcpy(req + j, name, (size_t)nlen + 1);
    j += (uint32_t)nlen + 1;
    const unsigned char rest[] = {0, 1, 0, AID_DATATYPE, 0, 4, 0xF0,
                                  (unsigned char)(l->m->is_89t ? 0x0C : 0x0B), 0,
                                  (unsigned char)strtoul(t, NULL, 16),
                                  0x01, /* Past the file protection */
                                  0, 0, 0, 0}; /* No new folder, no new name: delete */
    memcpy(req + j, rest, sizeof(rest));
    j += sizeof(rest);
    if (vpkt_send(l, VPKT_MODIF_VAR, req, j)) {
        printf("ERR rm: no answer\n");
        return 4;
    }
    if (expect_ack(l, "rm")) return 4;
    printf("OK removed\n");
    return 0;
}

/* ---- The clock (libticalcs: calc_84p.cc and calc_89t.cc, get_clock / set_clock). Only the
   date and time are read and set: the calculator's date and time formats and whether it shows
   the clock stay as they are. ---- */

/* One parameter's value in the answer to a parameter request; NULL when the calculator said
   it hasn't got it */
static const unsigned char *param_value(const unsigned char *d, uint32_t n, unsigned want,
                                        unsigned *size) {
    uint32_t p = 2;
    while (p + 3 <= n) {
        unsigned id = (d[p] << 8) | d[p + 1];
        int ok = d[p + 2] == 0;
        p += 3;
        if (!ok) {
            if (id == want) return NULL;
            continue;
        }
        if (p + 2 > n) return NULL;
        unsigned sz = (d[p] << 8) | d[p + 1];
        p += 2;
        if (p + sz > n) return NULL;
        if (id == want) {
            *size = sz;
            return d + p;
        }
        p += sz;
    }
    return NULL;
}

static unsigned long long now_ms(void) {
#ifdef _WIN32
    return GetTickCount64();
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (unsigned long long)ts.tv_sec * 1000 + (unsigned long long)ts.tv_nsec / 1000000;
#endif
}

static int leap(int y) { return (y % 4 == 0 && y % 100 != 0) || y % 400 == 0; }
static int month_days(int y, int m) {
    static const int days[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    return m == 2 && leap(y) ? 29 : days[m - 1];
}

/* The classic clock's count: seconds since 1997-01-01 00:00, in the calculator's own time (it
   has no time zone), so plain calendar arithmetic, no mktime() and no daylight saving */
static uint32_t secs_since_1997(int y, int mo, int d, int h, int mi, int s) {
    uint32_t days = 0;
    for (int k = 1997; k < y; k++) days += leap(k) ? 366 : 365;
    for (int k = 1; k < mo; k++) days += (uint32_t)month_days(y, k);
    days += (uint32_t)(d - 1);
    return ((days * 24 + (uint32_t)h) * 60 + (uint32_t)mi) * 60 + (uint32_t)s;
}

static void date_from_1997(uint32_t t, int *y, int *mo, int *d, int *h, int *mi, int *s) {
    *s = (int)(t % 60);
    t /= 60;
    *mi = (int)(t % 60);
    t /= 60;
    *h = (int)(t % 24);
    t /= 24;
    *y = 1997;
    while (t >= (uint32_t)(leap(*y) ? 366 : 365)) t -= leap((*y)++) ? 366 : 365;
    *mo = 1;
    while (t >= (uint32_t)month_days(*y, *mo)) t -= (uint32_t)month_days(*y, (*mo)++);
    *d = (int)t + 1;
}

/* "classic", "new", or NULL (no clock the link knows), from the answer d */
static const char *clock_kind(Link *l, const unsigned char *d, uint32_t n) {
    unsigned sz = 0;
    const unsigned char *c = param_value(d, n, PID_CLK_CLASSIC, &sz);
    if (l->m->is_89t) return c && sz >= 1 && c[0] ? "classic" : NULL;
    const unsigned char *nw = param_value(d, n, PID_CLK_NEW, &sz);
    if (c && !nw) return "classic";
    if (nw && !c) return "new";
    return NULL;
}

/* "clock": INFO clock=classic|new on=0|1 date_fmt=1|2|3 (M/D/Y, D/M/Y, Y/M/D) time_fmt=12|24,
   then INFO clock_date=YYYY-MM-DD clock_time=hh:mm:ss */
static int do_clock(Link *l) {
    static const uint16_t pids84[] = {PID_CLK_CLASSIC, PID_CLK_NEW, PID_CLK_ON, PID_CLK_SECS_1997,
                                      PID_CLK_DATE_FMT, PID_CLK_TIME_FMT, PID_CLK_SECONDS,
                                      PID_CLK_MINUTES, PID_CLK_HOURS, PID_CLK_DAY, PID_CLK_MONTH,
                                      PID_CLK_YEAR};
    static const uint16_t pids89[] = {PID_CLK_CLASSIC, PID_CLK_ON, PID_CLK_SECS_1997,
                                      PID_CLK_DATE_FMT, PID_CLK_TIME_FMT};
    const int t89 = l->m->is_89t;
    unsigned char *d = NULL;
    uint32_t n = 0;
    if (param_request(l, t89 ? pids89 : pids84, t89 ? 5 : 12, &d, &n)) {
        printf("ERR clock: no answer\n");
        return 4;
    }
    const char *kind = clock_kind(l, d, n);
    if (!kind) {
        printf("ERR clock: this calculator has no clock the link can read\n");
        free(d);
        return 4;
    }
    unsigned sz = 0;
    const unsigned char *on = param_value(d, n, PID_CLK_ON, &sz);
    int on_v = on && sz >= 1 ? on[0] != 0 : -1;
    const unsigned char *df = param_value(d, n, PID_CLK_DATE_FMT, &sz);
    int df_v = df && sz >= 1 ? (df[0] == 0 ? 3 : df[0]) : 0;
    const unsigned char *tf = param_value(d, n, PID_CLK_TIME_FMT, &sz);
    int tf_v = !tf || sz < 1 ? 0 : !strcmp(kind, "new") ? (tf[0] == 0x80 ? 12 : 24) : (tf[0] ? 24 : 12);
    int y = 0, mo = 0, dd = 0, h = 0, mi = 0, s = 0, ok = 0;
    if (!strcmp(kind, "classic")) {
        const unsigned char *v = param_value(d, n, PID_CLK_SECS_1997, &sz);
        if (v && sz == 4) {
            date_from_1997(be32(v), &y, &mo, &dd, &h, &mi, &s);
            ok = 1;
        }
    } else {
        static const uint16_t f[6] = {PID_CLK_YEAR, PID_CLK_MONTH, PID_CLK_DAY, PID_CLK_HOURS,
                                      PID_CLK_MINUTES, PID_CLK_SECONDS};
        int *out[6] = {&y, &mo, &dd, &h, &mi, &s};
        ok = 1;
        for (int i = 0; i < 6 && ok; i++) {
            const unsigned char *v = param_value(d, n, f[i], &sz);
            if (!v || sz != (i == 0 ? 2u : 1u)) ok = 0;
            else *out[i] = i == 0 ? (v[0] << 8) | v[1] : v[0];
        }
    }
    free(d);
    printf("INFO clock=%s on=%d date_fmt=%d time_fmt=%d\n", kind, on_v, df_v, tf_v);
    if (!ok) {
        printf("ERR clock: the calculator didn't send its time\n");
        return 4;
    }
    printf("INFO clock_date=%04d-%02d-%02d clock_time=%02d:%02d:%02d\n", y, mo, dd, h, mi, s);
    printf("OK\n");
    return 0;
}

static int param_set(Link *l, unsigned id, const unsigned char *v, unsigned size) {
    unsigned char b[4 + 8];
    if (size > 8) return 1;
    b[0] = (unsigned char)(id >> 8);
    b[1] = (unsigned char)id;
    b[2] = (unsigned char)(size >> 8);
    b[3] = (unsigned char)size;
    memcpy(b + 4, v, size);
    if (vpkt_send(l, VPKT_PARM_SET, b, 4 + size)) {
        printf("ERR setclock: no answer\n");
        return 4;
    }
    return expect_ack(l, "setclock");
}

/* The new clock's six fields (year, month, day, hours, minutes, seconds); -1 for one missing */
static int read_clock_fields(Link *l, int cur[6]) {
    static const uint16_t all[6] = {PID_CLK_YEAR, PID_CLK_MONTH, PID_CLK_DAY, PID_CLK_HOURS,
                                    PID_CLK_MINUTES, PID_CLK_SECONDS};
    unsigned char *a = NULL;
    uint32_t n = 0;
    if (param_request(l, all, 6, &a, &n)) {
        printf("ERR setclock: no answer\n");
        return 4;
    }
    for (int i = 0; i < 6; i++) {
        unsigned sz = 0;
        const unsigned char *v = param_value(a, n, all[i], &sz);
        cur[i] = !v ? -1 : sz == 2 ? (v[0] << 8) | v[1] : v[0];
    }
    free(a);
    return 0;
}

/* "setclock YYYY MM DD hh mm ss": the calculator's date and time (its own local time);
   "setclock now": the PC's local time when the command runs */
static int do_setclock(Link *l, const char *arg) {
    int y, mo, d, h, mi, s;
    if (!strcmp(arg, "now")) {
        time_t now = time(NULL);
        struct tm *t = localtime(&now);
        if (!t) {
            printf("ERR setclock: the PC's time can't be read\n");
            return 6;
        }
        y = t->tm_year + 1900;
        mo = t->tm_mon + 1;
        d = t->tm_mday;
        h = t->tm_hour;
        mi = t->tm_min;
        s = t->tm_sec > 59 ? 59 : t->tm_sec;
    } else if (sscanf(arg, "%d %d %d %d %d %d", &y, &mo, &d, &h, &mi, &s) != 6) {
        y = 0;
    }
    if (y < 1997 || y > 2100 ||
        mo < 1 || mo > 12 || d < 1 || d > month_days(y, mo) || h < 0 || h > 23 || mi < 0 ||
        mi > 59 || s < 0 || s > 59) {
        printf("ERR usage: setclock now | setclock YYYY MM DD hh mm ss (1997 to 2100)\n");
        return 1;
    }
    static const uint16_t pids[] = {PID_CLK_CLASSIC, PID_CLK_NEW};
    unsigned char *a = NULL;
    uint32_t n = 0;
    if (param_request(l, pids, l->m->is_89t ? 1 : 2, &a, &n)) {
        printf("ERR setclock: no answer\n");
        return 4;
    }
    const char *kind = clock_kind(l, a, n);
    free(a);
    if (!kind) {
        printf("ERR setclock: this calculator has no clock the link can set\n");
        return 4;
    }
    const uint32_t target = secs_since_1997(y, mo, d, h, mi, s);
    if (!strcmp(kind, "classic")) { /* One count: set at once */
        unsigned char v[4] = {(unsigned char)(target >> 24), (unsigned char)(target >> 16),
                              (unsigned char)(target >> 8), (unsigned char)target};
        int r = param_set(l, PID_CLK_SECS_1997, v, 4);
        if (r) return r;
        printf("OK clock set to %04d-%02d-%02d %02d:%02d:%02d (classic clock)\n", y, mo, d, h, mi, s);
        return 0;
    }
    /* The new clock, field by field. Measured on a TI-84 Plus CE, OS 5.4.0: each field written
       reaches the clock a moment later, and a field written before the last one has arrived is
       lost (the clock also stands still meanwhile). So each field is read back until it shows,
       and the time written moves on with the seconds this takes. */
    static const uint16_t ids[6] = {PID_CLK_YEAR, PID_CLK_MONTH, PID_CLK_DAY, PID_CLK_HOURS,
                                    PID_CLK_MINUTES, PID_CLK_SECONDS};
    const unsigned long long t0 = now_ms();
    int cur[6];
    if (read_clock_fields(l, cur)) return 4; /* What already matches (the date, mostly) stays */
    for (int pass = 0; pass < 2; pass++) {
        for (int i = 0; i < 6; i++) {
            /* The seconds go one ahead: the clock stands still until the write arrives */
            uint32_t t = target + (uint32_t)((now_ms() - t0) / 1000) + (i == 5);
            int f[6];
            date_from_1997(t, &f[0], &f[1], &f[2], &f[3], &f[4], &f[5]);
            if (i < 5 && cur[i] == f[i]) continue; /* Each field written costs about 1 s */
            unsigned char v[2];
            unsigned size = 1;
            if (i == 0) {
                v[0] = (unsigned char)(f[0] >> 8);
                v[1] = (unsigned char)f[0];
                size = 2;
            } else {
                v[0] = (unsigned char)f[i];
            }
            int r = param_set(l, ids[i], v, size);
            if (r) return r;
            /* Until it shows (up to 3 s); the seconds may have moved on by one meanwhile */
            for (int tries = 0; tries < 30; tries++) {
                unsigned char *a = NULL;
                uint32_t n = 0;
                unsigned sz = 0;
                if (param_request(l, &ids[i], 1, &a, &n)) {
                    printf("ERR setclock: no answer\n");
                    return 4;
                }
                const unsigned char *got = param_value(a, n, ids[i], &sz);
                int g = !got || sz != size ? -1 : size == 2 ? (got[0] << 8) | got[1] : got[0];
                free(a);
                if (g == f[i] || (i == 5 && g == (f[i] + 1) % 60)) break;
                sleep_ms(100);
            }
        }
        /* All six read back together: right unless a minute (or hour...) turned over */
        if (read_clock_fields(l, cur)) return 4;
        uint32_t want = target + (uint32_t)((now_ms() - t0) / 1000);
        if (cur[0] >= 1997 && cur[1] >= 1 && cur[1] <= 12 && cur[2] >= 1 && cur[2] <= 31 &&
            cur[3] >= 0 && cur[4] >= 0 && cur[5] >= 0) {
            uint32_t have = secs_since_1997(cur[0], cur[1], cur[2], cur[3], cur[4], cur[5]);
            long diff = (long)have - (long)want;
            if (diff >= -2 && diff <= 2) {
                printf("OK clock set to %04d-%02d-%02d %02d:%02d:%02d (new clock, %ld s off)\n",
                       cur[0], cur[1], cur[2], cur[3], cur[4], cur[5], diff);
                return 0;
            }
        }
    }
    printf("ERR setclock: the calculator's clock didn't take the time (it reads %04d-%02d-%02d "
           "%02d:%02d:%02d)\n", cur[0], cur[1], cur[2], cur[3], cur[4], cur[5]);
    return 4;
}

/* ---- Running a program, and the ROM dumper's own protocol (libticalcs: calc_89t.cc
   dump_rom_1/dump_rom_2, dusb_cmd.cc dusb_cmd_s_execute, romdump.cc rd_read_dump,
   docs/romdump.txt; GPL-2.0-or-later). Used by tools/pc_copy.py for the TI-89 Titanium; the
   TI-84 Plus CE's OS no longer runs a program from the link, so pc_copy types its keys. ---- */

#define PID_HOMESCREEN 0x0037

/* "home": back to the home screen (the 89 Titanium: calc_89t.cc dump_rom_1) */
static int do_home(Link *l) {
    unsigned char b[5] = {(unsigned char)(PID_HOMESCREEN >> 8), (unsigned char)PID_HOMESCREEN, 0, 1, 1};
    if (vpkt_send(l, VPKT_PARM_SET, b, sizeof(b))) {
        printf("ERR home: no answer\n");
        return 4;
    }
    if (expect_ack(l, "home")) return 4;
    printf("OK home\n");
    return 0;
}

/* "exec prgm|asm FOLDERHEX NAMEHEX": runs a program on the calculator (the 89 Titanium; the
   84 Plus CE answers with an error). The folder is "-" on the 84 family. */
static int do_exec(Link *l, char *arg) {
    char *kind = strtok(arg, " "), *fh = strtok(NULL, " "), *nh = strtok(NULL, " ");
    unsigned char folder[40], name[40];
    int flen = fh ? from_hex(fh, folder, sizeof(folder)) : -1;
    int nlen = nh ? from_hex(nh, name, sizeof(name)) : -1;
    if (!kind || (strcmp(kind, "prgm") && strcmp(kind, "asm")) || flen < 0 || nlen <= 0) {
        printf("ERR usage: exec prgm|asm FOLDERHEX NAMEHEX\n");
        return 1;
    }
    unsigned char e[96];
    uint32_t j = 0;
    e[j++] = (unsigned char)flen;
    if (l->m->is_89t && flen) {
        memcpy(e + j, folder, (size_t)flen + 1);
        j += (uint32_t)flen + 1;
    }
    e[j++] = (unsigned char)nlen;
    memcpy(e + j, name, (size_t)nlen + 1);
    j += (uint32_t)nlen + 1;
    e[j++] = (unsigned char)(strcmp(kind, "asm") ? 0x00 : 0x01); /* DUSB_EID_PRGM / _ASM */
    if (vpkt_send(l, VPKT_EXECUTE, e, j)) {
        printf("ERR exec: no answer\n");
        return 4;
    }
    if (expect_ack(l, "exec")) return 4;
    printf("OK exec\n");
    return 0;
}

enum {
    RD_IS_READY = 0xAA55, RD_KO = 0x0000, RD_OK = 0x0001, RD_EXIT = 0x0002, RD_REQ_SIZE = 0x0003,
    RD_ERROR = 0x0004, RD_REQ_BLOCK = 0x0005, RD_DATA = 0x0006, RD_DATA_RPT = 0x0007
};

/* One dumper packet: command (2, little endian), length (2), data, the byte sum (2) */
static int rd_send(Link *l, uint16_t cmd, const unsigned char *data, uint16_t len) {
    unsigned char b[16];
    uint16_t sum = 0;
    if (len > 8) return -1;
    b[0] = (unsigned char)cmd;
    b[1] = (unsigned char)(cmd >> 8);
    b[2] = (unsigned char)len;
    b[3] = (unsigned char)(len >> 8);
    if (len) memcpy(b + 4, data, len);
    for (int i = 0; i < 4 + len; i++) sum = (uint16_t)(sum + b[i]);
    b[4 + len] = (unsigned char)sum;
    b[5 + len] = (unsigned char)(sum >> 8);
    int sent = 0;
    return libusb_bulk_transfer(l->dev, l->ep_out, b, 6 + len, &sent, TIMEOUT_MS) == 0 &&
                   sent == 6 + len
               ? 0
               : -1;
}

/* 0 ok, -1 no answer / broken, -2 bad checksum (the bytes were all read: resync and retry) */
static int rd_recv(Link *l, uint16_t *cmd, unsigned char *data, uint16_t *len, uint16_t cap) {
    unsigned char h[4], s[2];
    if (usb_read(l, h, 4)) return -1;
    *cmd = (uint16_t)(h[0] | (h[1] << 8));
    *len = (uint16_t)(h[2] | (h[3] << 8));
    if (*len > cap) return -1;
    if ((*len && usb_read(l, data, *len)) || usb_read(l, s, 2)) return -1;
    uint16_t sum = 0;
    for (int i = 0; i < 4; i++) sum = (uint16_t)(sum + h[i]);
    for (unsigned i = 0; i < *len; i++) sum = (uint16_t)(sum + data[i]);
    return sum == (uint16_t)(s[0] | (s[1] << 8)) ? 0 : -2;
}

static int rd_ready(Link *l) {
    unsigned char d[16];
    uint16_t cmd = 0, len = 0;
    if (rd_send(l, RD_IS_READY, NULL, 0)) return -1;
    int r = rd_recv(l, &cmd, d, &len, sizeof(d));
    return r == 0 && cmd == RD_OK ? 0 : -1;
}

/* "romdump LOCAL": with the dumper already running on the calculator (exec), reads the whole
   ROM into LOCAL and tells the dumper to end. The 89 Titanium's certificate (0x10000-0x11FFF)
   is read protected and comes out as 0xFF, as TILP does. Prints PROGRESS lines and
   "OK romdump size=N blocks=B repeated=R". */
static int do_romdump(Link *l, const char *out) {
    int ok = 0;
    for (int tries = 0; tries < 10 && !ok; tries++) {
        if (rd_ready(l) == 0) ok = 1;
        else sleep_ms(500);
    }
    if (!ok) {
        printf("ERR romdump: the dumper didn't answer (is it running on the calculator?)\n");
        return 4;
    }
    unsigned char d[4096 + 16];
    uint16_t cmd = 0, len = 0;
    if (rd_send(l, RD_REQ_SIZE, NULL, 0) || rd_recv(l, &cmd, d, &len, sizeof(d)) || cmd != RD_REQ_SIZE ||
        len != 4) {
        printf("ERR romdump: the dumper didn't say the ROM's size\n");
        return 4;
    }
    uint32_t size = le32(d);
    if (size == 0 || size > 0x800000 || (size & 0xFFF)) {
        printf("ERR romdump: a ROM size of %lu bytes can't be right\n", (unsigned long)size);
        return 4;
    }
    FILE *f = fopen(out, "wb");
    if (!f) {
        printf("ERR cannot write %s\n", out);
        return 6;
    }
    unsigned blocks = 0, repeated = 0, errors = 0;
    uint32_t addr = 0;
    while (addr < size) {
        uint16_t blen = 4096;
        if (l->m->is_89t && addr >= 0x10000 && addr < 0x12000) {
            memset(d, 0xFF, blen); /* The certificate: read protected */
        } else {
            unsigned char a[4] = {(unsigned char)addr, (unsigned char)(addr >> 8),
                                  (unsigned char)(addr >> 16), (unsigned char)(addr >> 24)};
            int r = rd_send(l, RD_REQ_BLOCK, a, 4);
            if (!r) r = rd_recv(l, &cmd, d, &len, sizeof(d));
            if (!r && cmd == RD_DATA) {
                blen = len;
            } else if (!r && cmd == RD_DATA_RPT && len == 4) {
                blen = (uint16_t)(d[0] | (d[1] << 8));
                memset(d, d[2], blen > sizeof(d) ? sizeof(d) : blen);
                repeated++;
            } else {
                if (++errors > 20) {
                    fclose(f);
                    printf("ERR romdump: too many link errors at 0x%06lx\n", (unsigned long)addr);
                    return 4;
                }
                sleep_ms(500); /* Resync as rd_read_dump does, then ask for the same block */
                l->in_pos = l->in_len = 0;
                {
                    int got = 0;
                    unsigned char junk[1024];
                    while (libusb_bulk_transfer(l->dev, l->ep_in, junk, sizeof(junk), &got, 100) == 0 && got > 0) {
                    }
                }
                for (int t = 0; t < 3 && rd_ready(l); t++) {
                }
                continue;
            }
            if (blen == 0 || blen > 4096) {
                fclose(f);
                printf("ERR romdump: a block of %u bytes at 0x%06lx\n", (unsigned)blen, (unsigned long)addr);
                return 4;
            }
        }
        if (fwrite(d, 1, blen, f) != blen) {
            fclose(f);
            printf("ERR cannot write %s\n", out);
            return 6;
        }
        addr += blen;
        blocks++;
        if ((addr & 0xFFFF) == 0 || addr >= size)
            printf("PROGRESS %lu %lu\n", (unsigned long)addr, (unsigned long)size);
    }
    fclose(f);
    sleep_ms(200);
    if (rd_send(l, RD_EXIT, NULL, 0) || rd_recv(l, &cmd, d, &len, sizeof(d)) || cmd != RD_EXIT)
        printf("WARN romdump: the dumper didn't confirm it ended (press ESC on the calculator)\n");
    sleep_ms(1000);
    printf("OK romdump size=%lu blocks=%u repeated=%u retries=%u\n", (unsigned long)size, blocks, repeated,
           errors);
    return 0;
}

static int run_line(Link *l, char *line) {
    char *arg = strchr(line, ' ');
    if (arg) *arg++ = 0;
    if (!strcmp(line, "info")) return do_info(l);
    if (!strcmp(line, "home")) return do_home(l);
    if (!strcmp(line, "exec") && arg) return do_exec(l, arg);
    if (!strcmp(line, "romdump") && arg) return do_romdump(l, arg);
    if (!strcmp(line, "shot") && arg) return do_shot(l, arg);
    if (!strcmp(line, "ls")) return do_ls(l);
    if (!strcmp(line, "get") && arg) return do_get(l, arg);
    if (!strcmp(line, "put") && arg) return do_put(l, arg);
    if (!strcmp(line, "rm") && arg) return do_rm(l, arg);
    if (!strcmp(line, "send") && arg) return do_send(l, arg);
    if (!strcmp(line, "clock")) return do_clock(l);
    if (!strcmp(line, "setclock") && arg) return do_setclock(l, arg);
    if ((!strcmp(line, "key") || !strcmp(line, "keys")) && arg) {
        int n = 0;
        for (char *tok = strtok(arg, " "); tok; tok = strtok(NULL, " ")) {
            if (do_key(l, strtoul(tok, NULL, 16))) {
                printf("ERR key %s (after %d)\n", tok, n);
                return 4;
            }
            n++;
        }
        printf("OK keys %d\n", n);
        return 0;
    }
    printf("ERR unknown command\n");
    return 1;
}

static int usage(void) {
    printf("usage: ti84-cli [--model 84ce|89t|auto] info | shot FILE.ppm | key HEXCODE | send FILE |"
           " serve\n"
           "       ti84-cli devices\n");
    return 1;
}

/* Lists the TI calculators on USB from their descriptors: nothing is opened */
static int cmd_devices(void) {
    libusb_context *ctx = NULL;
    libusb_device **list = NULL;
    int found = 0;
    if (libusb_init(&ctx)) {
        printf("ERR libusb_init failed\n");
        return 3;
    }
    ssize_t cnt = libusb_get_device_list(ctx, &list);
    for (ssize_t i = 0; i < cnt; i++) {
        struct libusb_device_descriptor d;
        if (libusb_get_device_descriptor(list[i], &d) || d.idVendor != TI_VID) continue;
        const Model *m = model_of(d.idProduct, MODEL_AUTO);
        printf("DEVICE pid=%04x model=%s\n", d.idProduct, m ? m->name : "other");
        found++;
    }
    if (list) libusb_free_device_list(list, 1);
    libusb_exit(ctx);
    printf("OK %d\n", found);
    return found ? 0 : 2;
}

/* The model the program's name stands for: ti89-cli the 89 Titanium, any other the 84 */
static int model_from_name(const char *argv0) {
    const char *base = argv0;
    for (const char *p = argv0; *p; p++)
        if (*p == '/' || *p == '\\') base = p + 1;
    return strncmp(base, "ti89", 4) == 0 ? 1 : 0;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    int want = argc > 0 && argv[0] ? model_from_name(argv[0]) : 0;
    if (argc >= 3 && !strcmp(argv[1], "--model")) {
        want = -2;
        if (!strcmp(argv[2], "auto")) want = MODEL_AUTO;
        for (int i = 0; i < N_MODELS; i++)
            if (!strcmp(argv[2], MODELS[i].name)) want = i;
        if (want == -2) return usage();
        argv += 2;
        argc -= 2;
    }
    if (argc < 2) return usage();
    if (!strcmp(argv[1], "devices") && argc == 2) return cmd_devices();
    Link l;
    char line[2048];
    if (!strcmp(argv[1], "serve")) {
        int r = link_open(&l, want);
        printf("END %d\n", r);
        if (r) {
            link_close(&l);
            return r;
        }
        while (fgets(line, sizeof(line), stdin)) {
            size_t n = strlen(line);
            while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
            if (!n) continue;
            if (!strcmp(line, "quit")) break;
            printf("END %d\n", run_line(&l, line));
        }
        link_close(&l);
        return 0;
    }
    if ((!strcmp(argv[1], "info") || !strcmp(argv[1], "clock")) && argc == 2) {
        strcpy(line, argv[1]);
    } else if ((!strcmp(argv[1], "shot") || !strcmp(argv[1], "key") || !strcmp(argv[1], "send")) &&
               argc == 3) {
        snprintf(line, sizeof(line), "%s %s", argv[1], argv[2]);
    } else {
        return usage();
    }
    int r = link_open(&l, want);
    if (!r) r = run_line(&l, line);
    link_close(&l);
    return r;
}
