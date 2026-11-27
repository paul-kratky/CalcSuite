// SPDX-License-Identifier: GPL-3.0-or-later
/*
 * ti84-cli: a small USB link for the TI-84 Plus CE family (TI's "DUSB" protocol) on libusb.
 *
 *   ti84-cli info               connect and print the model, OS version and free memory
 *   ti84-cli shot FILE.ppm      save the screen as a PPM picture
 *   ti84-cli key HEXCODE        press one key (a TI-OS key code, see ti84_keys.py)
 *   ti84-cli serve              one connection, commands on stdin, one per line:
 *                               info | shot FILE | key HEX | keys HEX HEX ... | quit
 *                               each ends with "END <code>" (as nspire-cli serve does)
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

enum { RPKT_BUF_REQ = 1, RPKT_BUF_ALLOC = 2, RPKT_DATA = 3, RPKT_DATA_LAST = 4, RPKT_ACK = 5 };
enum {
    VPKT_PING = 0x0001, VPKT_PARM_REQ = 0x0007, VPKT_PARM_DATA = 0x0008, VPKT_EXECUTE = 0x0011,
    VPKT_MODE_SET = 0x0012, VPKT_DATA_ACK = 0xAA00, VPKT_DELAY_ACK = 0xBB00, VPKT_ERROR = 0xEE00
};
enum {
    PID_PRODUCT_NAME = 0x0002, PID_OS_VERSION = 0x000B, PID_FREE_RAM = 0x000E,
    PID_FREE_FLASH = 0x0011, PID_SCREENSHOT = 0x0022, PID_BATTERY = 0x002D
};

#define RAW_MAX 1023
#define TIMEOUT_MS 5000

typedef struct {
    libusb_context *ctx;
    libusb_device_handle *dev;
    unsigned char ep_in, ep_out;
    uint32_t maxlen;             /* The raw packet payload both sides agreed on */
    unsigned char inbuf[4096];   /* Bytes read from USB, not yet consumed */
    int in_len, in_pos;
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
       exactly (libticalcs: workaround_send) */
    if (type == RPKT_DATA_LAST && ((n + 5) % 64) == 0)
        libusb_bulk_transfer(l->dev, l->ep_out, buf, 0, &sent, TIMEOUT_MS);
    return 0;
}

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
    if (n <= first) {
        if (n) memcpy(raw + 6, data, n);
        if (raw_send(l, RPKT_DATA_LAST, raw, n + 6)) return -1;
        return recv_ack(l);
    }
    memcpy(raw + 6, data, first);
    if (raw_send(l, RPKT_DATA, raw, l->maxlen) || recv_ack(l)) return -1;
    uint32_t off = first;
    while (off < n) {
        uint32_t take = n - off > l->maxlen ? l->maxlen : n - off;
        int last = (off + take == n);
        if (raw_send(l, last ? RPKT_DATA_LAST : RPKT_DATA, data + off, take) || recv_ack(l)) return -1;
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
            len += rn;
            if (send_ack(l)) {
                free(buf);
                return -1;
            }
        } while (rtype != RPKT_DATA_LAST);
        if (*vtype == VPKT_DELAY_ACK && len >= 4) {
            uint32_t us = ((uint32_t)buf[0] << 24) | ((uint32_t)buf[1] << 16) | ((uint32_t)buf[2] << 8) | buf[3];
            if (us > 400000) us = 400000;
            sleep_ms(us / 1000);
            free(buf);
            continue;
        }
        *out = buf;
        *n = len;
        return 0;
    }
    return -1;
}

static int link_open(Link *l) {
    memset(l, 0, sizeof(*l));
    if (libusb_init(&l->ctx)) {
        printf("ERR libusb_init failed\n");
        return 3;
    }
    libusb_device **list = NULL;
    ssize_t cnt = libusb_get_device_list(l->ctx, &list);
    int found = 0, rc = 2;
    for (ssize_t i = 0; i < cnt && !l->dev; i++) {
        struct libusb_device_descriptor d;
        if (libusb_get_device_descriptor(list[i], &d) || d.idVendor != TI_VID || d.idProduct != PID_84P)
            continue;
        found = 1;
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
        if (!found) printf("ERR no TI-84 Plus family calculator on USB\n");
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

    /* The handshake: agree a buffer size, then "normal mode" */
    unsigned char b[4] = {0, 0, 0x04, 0x00}; /* 1024 */
    unsigned char d[RAW_MAX];
    uint32_t n;
    int type;
    if (raw_send(l, RPKT_BUF_REQ, b, 4) || raw_recv(l, &type, d, &n) || type != RPKT_BUF_ALLOC || n != 4) {
        printf("ERR the calculator did not answer (is it on, at the home screen?)\n");
        return 4;
    }
    l->maxlen = ((uint32_t)d[0] << 24) | ((uint32_t)d[1] << 16) | ((uint32_t)d[2] << 8) | d[3];
    if (l->maxlen > 1018) l->maxlen = 1018; /* The CE allocates more than it handles */
    if (l->maxlen < 64) l->maxlen = 250;
    static const unsigned char mode[10] = {0, 3, 0, 1, 0, 0, 0, 0, 0x07, 0xD0};
    unsigned char *ans = NULL;
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
    unsigned char req[2 + 2 * 8];
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
        } else if (id == PID_OS_VERSION && sz >= 4) {
            printf("INFO os=%u.%u.%u.%u\n", v[0], v[1], v[2], v[3]);
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
    if ((code >> 8) == 0) { /* A one-byte key: high byte first (the eZ80 OS needs that) */
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

static int run_line(Link *l, char *line) {
    char *arg = strchr(line, ' ');
    if (arg) *arg++ = 0;
    if (!strcmp(line, "info")) return do_info(l);
    if (!strcmp(line, "shot") && arg) return do_shot(l, arg);
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
    printf("usage: ti84-cli info | shot FILE.ppm | key HEXCODE | serve\n");
    return 1;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc < 2) return usage();
    Link l;
    char line[2048];
    if (!strcmp(argv[1], "serve")) {
        int r = link_open(&l);
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
    if (!strcmp(argv[1], "info") && argc == 2) {
        strcpy(line, "info");
    } else if ((!strcmp(argv[1], "shot") || !strcmp(argv[1], "key")) && argc == 3) {
        snprintf(line, sizeof(line), "%s %s", argv[1], argv[2]);
    } else {
        return usage();
    }
    int r = link_open(&l);
    if (!r) r = run_line(&l, line);
    link_close(&l);
    return r;
}
