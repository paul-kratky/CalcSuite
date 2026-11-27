// SPDX-License-Identifier: GPL-3.0-or-later (links libnspire; see COPYING in this folder)
/*
 * nspire-cli: a small command-line front end for libnspire (TI-Nspire USB link).
 *
 *   nspire-cli devices            list TI USB devices and whether they can be opened
 *   nspire-cli info               connect and print the handheld's name, OS and free space
 *   nspire-cli ls [PATH]          list a folder on the handheld ("/" = My Documents)
 *   nspire-cli mkdir PATH         create a folder (no error if it exists)
 *   nspire-cli put LOCAL REMOTE   upload a file, then read it back and compare
 *   nspire-cli get REMOTE LOCAL   download a file
 *   nspire-cli rm PATH            delete a file or an empty folder
 *   nspire-cli mv SRC DST         rename or move a file or folder
 *   nspire-cli shot FILE.ppm      save the handheld's screen as a PPM picture
 *   nspire-cli key HEXCODE        press one key (a 3-byte code, see nspire_keys.py)
 *   nspire-cli serve              one long connection: commands on stdin, one per line
 *                                 (info | ls PATH | mkdir PATH | put LOCAL|REMOTE |
 *                                 get REMOTE|LOCAL | rm PATH | mv SRC|DST |
 *                                 shot FILE | key HEX | keys HEX HEX ... | quit); each
 *                                 ends with "END <code>". A download prints
 *                                 "PROGRESS <bytes> <total>" lines as it goes.
 *
 * The CX II does its address handshake once per plug-in and is silent after that. Our copy of
 * libnspire's cx2.cpp (cx2_resume.cpp) asks it to start over, so a second run connects too.
 * `serve` is still the fast way to do several things: one handshake for all of them.
 *
 * Exit codes: 0 ok, 1 usage error, 2 no handheld found, 3 driver/open problem,
 *             4 link/protocol error, 5 verify failed, 6 local file error.
 *
 * Built by tools/build_tools.py against third_party/libnspire and third_party/libusb-*.
 * Because it links libnspire (GPL-3.0-or-later), the resulting nspire-cli.exe is
 * GPL-3.0-or-later too; this file is offered under the same licence.
 * Every line printed starts with a tag (OK/ERR/DEV/INFO/ITEM/END) so the Python tools
 * can parse it.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <libusb.h>

#include "nspire.h"
#include "screenshot.h"
/* libnspire internals, for the key-press service it has no API for */
#include "handle.h"
#include "service.h"
#include "data.h"

#define TI_VID 0x0451

static const char *model_for_pid(int pid) {
    switch (pid) {
        case 0xe012: return "TI-Nspire (CX / Clickpad / Touchpad)";
        case 0xe022: return "TI-Nspire CX II family";
        case 0xe003: case 0xe008: return "TI-84 Plus (not an Nspire)";
        case 0xe001: return "TI-GRAPH LINK USB cable";
        default: return "other TI device";
    }
}

static int cmd_devices(void) {
    libusb_context *ctx = NULL;
    libusb_device **list = NULL;
    int found = 0, usable = 0;
    if (libusb_init(&ctx) != 0) {
        printf("ERR libusb_init failed\n");
        return 3;
    }
    ssize_t n = libusb_get_device_list(ctx, &list);
    for (ssize_t i = 0; i < n; i++) {
        struct libusb_device_descriptor d;
        if (libusb_get_device_descriptor(list[i], &d) != 0) continue;
        if (d.idVendor != TI_VID) continue;
        found++;
        libusb_device_handle *h = NULL;
        int r = libusb_open(list[i], &h);
        const char *state;
        if (r == 0) {
            state = "ok";
            usable++;
            libusb_close(h);
        } else if (r == LIBUSB_ERROR_NOT_SUPPORTED) {
            state = "no-winusb-driver";
        } else if (r == LIBUSB_ERROR_ACCESS) {
            state = "busy-or-access-denied";
        } else {
            state = libusb_error_name(r);
        }
        printf("DEV vid=%04x pid=%04x bus=%d addr=%d model=\"%s\" open=%s\n", d.idVendor,
               d.idProduct, libusb_get_bus_number(list[i]), libusb_get_device_address(list[i]),
               model_for_pid(d.idProduct), state);
    }
    if (list) libusb_free_device_list(list, 1);
    libusb_exit(ctx);
    if (!found) {
        printf("ERR no TI device on USB\n");
        return 2;
    }
    if (!usable) {
        printf("ERR TI device found but it cannot be opened (driver)\n");
        return 3;
    }
    printf("OK %d device(s)\n", found);
    return 0;
}

static int open_handle(nspire_handle_t **h) {
    int r = nspire_init(h);
    if (r) {
        int e = -r;
        printf("ERR connect: %s (code %d)\n", nspire_strerror(r), e);
        if (e == NSPIRE_ERR_NODEVICE || e == NSPIRE_ERR_LIBUSB) return 2;
        return 4;
    }
    return 0;
}

/* The service `serve` keeps open between commands (0: none): the key service (0x4042), so
   typing doesn't pay a disconnect round trip per command. Any other command closes it first
   (libnspire has one service per handle).
   The screenshot service is NOT kept: tried on a CX II CAS (OS 6.40), a second frame on one
   connection saves only ~1.5 ms of a ~55 ms frame, and every 60-400 frames the handheld acks
   the request and never answers it (a fresh connection then works). Detecting that costs
   more than the reuse saves, so each frame has its own connection, as before. */
static uint16_t kept_sid;

static void close_kept(nspire_handle_t *h) {
    if (h->connected) service_disconnect(h); /* A failed disconnect still leaves it closed here */
    h->connected = 0;
    kept_sid = 0;
}

static int keep_open(nspire_handle_t *h, uint16_t sid) {
    if (kept_sid == sid && h->connected) return 0;
    close_kept(h);
    int r = service_connect(h, sid);
    if (!r) kept_sid = sid;
    return r;
}

static const char *hw_name(int t) {
    switch (t) {
        case NSPIRE_CAS: return "CAS";
        case NSPIRE_NONCAS: return "non-CAS";
        case NSPIRE_CASCX: return "CX CAS";
        case NSPIRE_NONCASCX: return "CX";
        default: return "unknown";
    }
}

static int do_info(nspire_handle_t *h) {
    struct nspire_devinfo i;
    memset(&i, 0, sizeof(i));
    int r = nspire_device_info(h, &i);
    if (r) {
        printf("ERR device info: %s\n", nspire_strerror(r));
        return 4;
    }
    printf("INFO name=%.20s\n", i.device_name);
    printf("INFO id=%.28s\n", i.electronic_id);
    printf("INFO os=%u.%u.%u\n", i.versions[NSPIRE_VER_OS].major, i.versions[NSPIRE_VER_OS].minor,
           i.versions[NSPIRE_VER_OS].build);
    printf("INFO hw_type=0x%02x (%s)\n", (unsigned)i.hw_type, hw_name(i.hw_type));
    printf("INFO storage_free=%llu storage_total=%llu\n", (unsigned long long)i.storage.free,
           (unsigned long long)i.storage.total);
    printf("INFO battery=%s charging=%u\n",
           i.batt.status == NSPIRE_BATT_LOW ? "low"
           : i.batt.status == NSPIRE_BATT_OK ? "ok"
           : i.batt.status == NSPIRE_BATT_POWERED ? "powered" : "unknown",
           (unsigned)i.batt.is_charging);
    printf("INFO file_ext=%.8s\n", i.extensions.file);
    printf("OK\n");
    return 0;
}

static int do_ls(nspire_handle_t *h, const char *path) {
    struct nspire_dir_info *d = NULL;
    int r = nspire_dirlist(h, path, &d);
    if (r) {
        printf("ERR ls %s: %s\n", path, nspire_strerror(r));
        return 4;
    }
    for (unsigned long k = 0; k < d->num; k++) {
        printf("ITEM %s %lu %s\n", d->items[k].type == NSPIRE_DIR ? "dir" : "file",
               d->items[k].size, d->items[k].name);
    }
    printf("OK %lu item(s)\n", d->num);
    nspire_dirlist_free(d);
    return 0;
}

static int do_mkdir(nspire_handle_t *h, const char *path) {
    struct nspire_dir_item it;
    if (nspire_attr(h, path, &it) == 0 && it.type == NSPIRE_DIR) {
        printf("OK exists %s\n", path);
        return 0;
    }
    int r = nspire_dir_create(h, path);
    if (r) {
        printf("ERR mkdir %s: %s\n", path, nspire_strerror(r));
        return 4;
    }
    printf("OK created %s\n", path);
    return 0;
}

static int do_put(nspire_handle_t *h, const char *local, const char *remote) {
    FILE *f = fopen(local, "rb");
    if (!f) {
        printf("ERR cannot open local file %s\n", local);
        return 6;
    }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size <= 0) {
        fclose(f);
        printf("ERR local file is empty: %s\n", local);
        return 6;
    }
    unsigned char *buf = malloc((size_t)size);
    unsigned char *back = malloc((size_t)size + 16);
    if (!buf || !back || fread(buf, 1, (size_t)size, f) != (size_t)size) {
        fclose(f);
        printf("ERR cannot read local file %s\n", local);
        return 6;
    }
    fclose(f);

    int ret = 0;
    int r = nspire_file_write(h, remote, buf, (size_t)size);
    if (r) {
        printf("ERR upload %s: %s\n", remote, nspire_strerror(r));
        ret = 4;
        goto done;
    }
    printf("INFO sent %ld bytes to %s\n", size, remote);

    /* Check the size first: libnspire's file read does not bound its copy by the
       buffer size, so never read back more than we allocated. */
    struct nspire_dir_item it;
    r = nspire_attr(h, remote, &it);
    if (r) {
        printf("ERR verify: cannot stat %s: %s\n", remote, nspire_strerror(r));
        ret = 5;
        goto done;
    }
    if (it.size != (unsigned long)size) {
        printf("ERR verify: handheld has %lu bytes, expected %ld\n", it.size, size);
        ret = 5;
        goto done;
    }
    size_t got = 0;
    r = nspire_file_read(h, remote, back, (size_t)size + 16, &got);
    if (r) {
        printf("ERR read-back %s: %s\n", remote, nspire_strerror(r));
        ret = 5;
        goto done;
    }
    if (got != (size_t)size || memcmp(buf, back, (size_t)size) != 0) {
        printf("ERR verify: handheld has %lu bytes, expected %ld (or contents differ)\n",
               (unsigned long)got, size);
        ret = 5;
        goto done;
    }
    printf("OK verified %ld bytes at %s\n", size, remote);
done:
    free(buf);
    free(back);
    return ret;
}

/* Downloads a file. libnspire's nspire_file_read copies past the end of a buffer that is too
   small, and says nothing until the end; this loop (the same packets: 0x0701, then 0x04, the
   data, 0xFF00) writes straight to the file and prints "PROGRESS <bytes> <total>" as it goes. */
static int do_get(nspire_handle_t *h, const char *remote, const char *local) {
    struct nspire_dir_item it;
    int r = nspire_attr(h, remote, &it);
    if (r) {
        printf("ERR get %s: %s\n", remote, nspire_strerror(r));
        return 4;
    }
    if (it.type == NSPIRE_DIR) {
        printf("ERR get %s: it is a folder\n", remote);
        return 1;
    }
    FILE *f = fopen(local, "wb");
    if (!f) {
        printf("ERR cannot write %s\n", local);
        return 6;
    }
    const size_t cap = packet_max_datasize(h) + 1;
    uint8_t *buf = malloc(cap > 256 ? cap : 256);
    if (!buf) {
        fclose(f);
        printf("ERR out of memory\n");
        return 6;
    }
    int ret = 4;
    size_t len = 0, done = 0, last = 0;
    uint16_t result = 0;
    uint32_t data_len = 0;
    if ((r = service_connect(h, 0x4060))) {
        printf("ERR get %s: %s\n", remote, nspire_strerror(r));
        free(buf);
        fclose(f);
        remove(local);
        return 4;
    }
    if ((r = data_build("hs", buf, cap, &len, 0x0701, remote)) || (r = data_write(h, buf, len)) ||
        (r = data_read(h, buf, cap - 1, NULL)) ||
        (r = data_scan("h000000000w", buf, cap - 1, &result, &data_len)))
        goto end;
    if (result != 0x0301) {
        r = -NSPIRE_ERR_NONEXIST;
        goto end;
    }
    if ((r = data_write8(h, 0x04))) goto end;
    const size_t maxsize = packet_max_datasize(h) - 1;
    printf("PROGRESS 0 %lu\n", (unsigned long)data_len);
    while (data_len) {
        size_t want = maxsize < data_len ? maxsize : data_len, got = 0;
        if ((r = data_read(h, buf, want + 1, &got))) goto end;
        if (got < 1 || got - 1 > data_len) {
            r = -NSPIRE_ERR_INVALID;
            goto end;
        }
        if (fwrite(buf + 1, 1, got - 1, f) != got - 1) {
            printf("ERR cannot write %s\n", local);
            ret = 6;
            r = 0;
            goto end;
        }
        data_len -= (uint32_t)(got - 1);
        done += got - 1;
        if (done - last >= 32768) {
            printf("PROGRESS %lu %lu\n", (unsigned long)done, (unsigned long)(done + data_len));
            last = done;
        }
    }
    if ((r = data_write16(h, 0xFF00))) goto end;
    ret = 0;
end:
    service_disconnect(h);
    free(buf);
    if (fclose(f) && !ret) {
        printf("ERR cannot write %s\n", local);
        ret = 6;
    }
    if (ret) {
        if (r) printf("ERR get %s: %s\n", remote, nspire_strerror(r));
        remove(local);
        return ret;
    }
    printf("OK got %lu bytes %s\n", (unsigned long)done, local);
    return 0;
}

/* Deletes a file, or an empty folder */
static int do_rm(nspire_handle_t *h, const char *path) {
    struct nspire_dir_item it;
    int r = nspire_attr(h, path, &it);
    if (r) {
        printf("ERR rm %s: %s\n", path, nspire_strerror(r));
        return 4;
    }
    r = it.type == NSPIRE_DIR ? nspire_dir_delete(h, path) : nspire_file_delete(h, path);
    if (r) {
        printf("ERR rm %s: %s%s\n", path, nspire_strerror(r),
               it.type == NSPIRE_DIR ? " (a folder must be empty)" : "");
        return 4;
    }
    printf("OK removed %s\n", path);
    return 0;
}

/* Renames or moves a file or folder; refuses to replace one that exists */
static int do_mv(nspire_handle_t *h, const char *src, const char *dst) {
    struct nspire_dir_item it;
    if (nspire_attr(h, dst, &it) == 0) {
        printf("ERR mv: %s already exists\n", dst);
        return 4;
    }
    int r = nspire_file_move(h, src, dst);
    if (r) {
        printf("ERR mv %s: %s\n", src, nspire_strerror(r));
        return 4;
    }
    printf("OK moved %s to %s\n", src, dst);
    return 0;
}

/* libnspire's screenshot RLE (services/screenshot.c, static there) */
static void rle_decode(const uint8_t bpp, const uint8_t *in, uint8_t *out, size_t in_size,
                       size_t out_size) {
    const size_t rle_size = (bpp * 2) / 8; /* 2 pixels */
    while (in_size > 1 && out_size) {
        int len = (int8_t)*in++;
        in_size--;
        if (len < 0) {
            size_t n = (size_t)(-len + 1) * rle_size;
            n = n < out_size ? n : out_size;
            n = n < in_size ? n : in_size;
            memcpy(out, in, n);
            in_size -= n;
            in += n;
            out_size -= n;
            out += n;
        } else {
            if (in_size < rle_size) return;
            for (int i = 0; i < len + 1 && out_size >= rle_size; ++i) {
                memcpy(out, in, rle_size);
                out_size -= rle_size;
                out += rle_size;
            }
            in_size -= rle_size;
            in += rle_size;
        }
    }
}

/* One frame on the screenshot service, which must be open: libnspire's nspire_screenshot
   without its connect and disconnect, and bounded by what each packet really holds */
static int shot_frame(nspire_handle_t *h, struct nspire_image **ptr) {
    const size_t cap = packet_max_datasize(h);
    uint8_t *buffer = malloc(cap), *tmp = NULL, bpp = 0;
    uint16_t width = 0, height = 0;
    uint32_t size = 0;
    struct nspire_image *img = NULL;
    int r;
    if (!buffer) return -NSPIRE_ERR_NOMEM;
    if ((r = data_write8(h, 0x00)) || (r = data_read(h, buffer, cap, NULL)) ||
        (r = data_scan("bwhhhhbb", buffer, cap, NULL, &size, NULL, NULL, &width, &height, &bpp,
                       NULL)))
        goto end;
    if (!size || size > 4u * 1024 * 1024 || !width || !height || !bpp || bpp > 32) {
        r = -NSPIRE_ERR_INVALPKT;
        goto end;
    }
    const size_t in_len = size, out_len = ((size_t)width * height * bpp) / 8;
    tmp = malloc(in_len);
    img = malloc(sizeof(*img) + out_len);
    if (!tmp || !img) {
        r = -NSPIRE_ERR_NOMEM;
        goto end;
    }
    img->width = width;
    img->height = height;
    img->bpp = bpp;
    memset(img->data, 0, out_len);
    const size_t maxsize = cap - 1;
    uint8_t *p = tmp;
    while (size) {
        size_t got = 0;
        if ((r = data_read(h, buffer, cap, &got))) goto end;
        if (got < 1) {
            r = -NSPIRE_ERR_INVALPKT;
            goto end;
        }
        size_t len = maxsize < size ? maxsize : size;
        if (len > got - 1) len = got - 1;
        memcpy(p, buffer + 1, len);
        p += len;
        size -= (uint32_t)len;
    }
    rle_decode(bpp, tmp, img->data, in_len, out_len);
    *ptr = img;
    img = NULL;
    r = 0;
end:
    free(img);
    free(tmp);
    free(buffer);
    return r;
}

/* A frame on its own screenshot connection (see kept_sid); one more try if it fails */
static int grab_frame(nspire_handle_t *h, struct nspire_image **img) {
    int r = keep_open(h, 0x4024);
    if (!r) r = shot_frame(h, img);
    close_kept(h);
    if (r) {
        r = keep_open(h, 0x4024);
        if (!r) r = shot_frame(h, img);
        close_kept(h);
    }
    return r;
}

/* The screen as a binary PPM (P6, 8-bit RGB): Tk and most viewers read it as it is */
static int do_shot(nspire_handle_t *h, const char *out) {
    struct nspire_image *img = NULL;
    int r = grab_frame(h, &img);
    if (r || !img) {
        printf("ERR screenshot: %s\n", nspire_strerror(r));
        return 4;
    }
    const size_t px = (size_t)img->width * img->height;
    unsigned char *rgb = malloc(px * 3);
    if (!rgb) {
        free(img);
        printf("ERR out of memory\n");
        return 6;
    }
    if (img->bpp == 16) {
        for (size_t k = 0; k < px; k++) {
            unsigned v = img->data[2 * k] | ((unsigned)img->data[2 * k + 1] << 8); /* RGB565, low byte first */
            unsigned r5 = (v >> 11) & 31, g6 = (v >> 5) & 63, b5 = v & 31;
            rgb[3 * k] = (unsigned char)((r5 << 3) | (r5 >> 2));
            rgb[3 * k + 1] = (unsigned char)((g6 << 2) | (g6 >> 4));
            rgb[3 * k + 2] = (unsigned char)((b5 << 3) | (b5 >> 2));
        }
    } else if (img->bpp == 8) {
        for (size_t k = 0; k < px; k++) rgb[3 * k] = rgb[3 * k + 1] = rgb[3 * k + 2] = img->data[k];
    } else if (img->bpp == 4) { /* The grey models: 2 pixels a byte */
        for (size_t k = 0; k < px; k++) {
            unsigned v = (k & 1) ? (img->data[k / 2] & 15u) : (unsigned)(img->data[k / 2] >> 4);
            rgb[3 * k] = rgb[3 * k + 1] = rgb[3 * k + 2] = (unsigned char)(v * 17);
        }
    } else {
        printf("ERR screenshot: %u bits per pixel is not handled\n", (unsigned)img->bpp);
        free(rgb);
        free(img);
        return 4;
    }
    FILE *f = fopen(out, "wb");
    if (!f) {
        printf("ERR cannot write %s\n", out);
        free(rgb);
        free(img);
        return 6;
    }
    fprintf(f, "P6\n%u %u\n255\n", (unsigned)img->width, (unsigned)img->height);
    fwrite(rgb, 1, px * 3, f);
    fclose(f);
    printf("OK shot %ux%u bpp=%u %s\n", (unsigned)img->width, (unsigned)img->height,
           (unsigned)img->bpp, out);
    free(rgb);
    free(img);
    return 0;
}

/* Key presses through the key service (0x4042), which stays open between `key` and `keys`
   commands. libnspire has no call for it; the packets are the ones TILP's libticalcs sends
   (nsp_cmd_s_key): 01 00 00 80, then the key. The CX II (OS 6.4) needs both for every key:
   a key without its own 01 00 00 80 is dropped, and the two in one packet do nothing (tried).
   code = 0xAABBCC. Returns 0 or a libnspire error. */
static int send_keys(nspire_handle_t *h, char *list, int *sent) {
    int r = keep_open(h, 0x4042);
    for (char *tok = strtok(list, " "); tok && !r; tok = strtok(NULL, " ")) {
        unsigned char p1[4] = {0x01, 0x00, 0x00, 0x80};
        unsigned long code = strtoul(tok, NULL, 16);
        unsigned char p2[26];
        memset(p2, 0, sizeof(p2));
        p2[1 + 3] = 0x08;
        p2[1 + 4] = 0x02;
        p2[1 + 5] = (unsigned char)(code >> 16);
        p2[1 + 7] = (unsigned char)(code >> 8);
        p2[1 + 23] = (unsigned char)code;
        r = data_write(h, p1, sizeof(p1));
        if (!r) r = data_write(h, p2, sizeof(p2));
        if (!r) (*sent)++;
    }
    if (r) close_kept(h); /* The next command starts on a fresh connection */
    return r;
}

/* One key press ("key 616600") */
static int do_key(nspire_handle_t *h, char *arg) {
    int n = 0;
    unsigned long code = strtoul(arg, NULL, 16);
    int r = send_keys(h, arg, &n);
    if (r || n != 1) {
        printf("ERR key %06lx: %s\n", code, nspire_strerror(r));
        return 4;
    }
    printf("OK key %06lx\n", code);
    return 0;
}

/* Several key presses in one command ("keys 616600 624600 ...") */
static int do_keys(nspire_handle_t *h, char *list) {
    int n = 0;
    int r = send_keys(h, list, &n);
    if (r) {
        printf("ERR keys after %d: %s\n", n, nspire_strerror(r));
        return 4;
    }
    printf("OK keys %d\n", n);
    return 0;
}

/* One command line on an open connection. "put" splits LOCAL|REMOTE on the bar (paths may
   have spaces). */
static int run_line(nspire_handle_t *h, char *line) {
    char *arg = strchr(line, ' ');
    if (arg) *arg++ = 0;
    const int keyish = !strcmp(line, "key") || !strcmp(line, "keys");
    if (strcmp(line, "shot") && !keyish) close_kept(h); /* The others open their own service */
    if (!strcmp(line, "info")) return do_info(h);
    if (!strcmp(line, "ls")) return do_ls(h, arg && *arg ? arg : "/");
    if (!strcmp(line, "mkdir") && arg) return do_mkdir(h, arg);
    if (!strcmp(line, "shot") && arg) return do_shot(h, arg);
    if (!strcmp(line, "key") && arg) return do_key(h, arg);
    if (!strcmp(line, "keys") && arg) return do_keys(h, arg);
    if (!strcmp(line, "rm") && arg) return do_rm(h, arg);
    if ((!strcmp(line, "put") || !strcmp(line, "get") || !strcmp(line, "mv")) && arg) {
        char *bar = strchr(arg, '|');
        if (bar) {
            *bar++ = 0;
            if (!strcmp(line, "put")) return do_put(h, arg, bar);
            if (!strcmp(line, "get")) return do_get(h, arg, bar);
            return do_mv(h, arg, bar);
        }
    }
    printf("ERR unknown command\n");
    return 1;
}

static int cmd_serve(void) {
    nspire_handle_t *h;
    int r = open_handle(&h);
    printf("END %d\n", r); /* The connection's own result, before any command */
    if (r) return r;
    char line[2048];
    while (fgets(line, sizeof(line), stdin)) {
        size_t n = strlen(line);
        while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
        if (!n) continue;
        if (!strcmp(line, "quit")) break;
        printf("END %d\n", run_line(h, line));
    }
    close_kept(h);
    nspire_free(h);
    return 0;
}

/* A one-shot command: its own connection (see the note at the top) */
static int once(char *line) {
    nspire_handle_t *h;
    int r = open_handle(&h);
    if (r) return r;
    r = run_line(h, line);
    close_kept(h);
    nspire_free(h);
    return r;
}

static int usage(void) {
    printf("usage: nspire-cli devices | info | ls [PATH] | mkdir PATH | put LOCAL REMOTE |\n"
           "       get REMOTE LOCAL | rm PATH | mv SRC DST | shot FILE.ppm | key HEXCODE | serve\n"
           "PATH is on the handheld; \"/\" is the top of My Documents.\n");
    return 1;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc < 2) return usage();
    const char *c = argv[1];
    char line[2048];
    if (!strcmp(c, "devices")) return cmd_devices();
    if (!strcmp(c, "serve")) return cmd_serve();
    if (!strcmp(c, "info")) {
        strcpy(line, "info");
        return once(line);
    }
    if (!strcmp(c, "ls")) {
        snprintf(line, sizeof(line), "ls %s", argc > 2 ? argv[2] : "/");
        return once(line);
    }
    if ((!strcmp(c, "mkdir") || !strcmp(c, "shot") || !strcmp(c, "key") || !strcmp(c, "rm")) &&
        argc == 3) {
        snprintf(line, sizeof(line), "%s %s", c, argv[2]);
        return once(line);
    }
    if ((!strcmp(c, "get") || !strcmp(c, "mv")) && argc == 4) {
        snprintf(line, sizeof(line), "%s %s|%s", c, argv[2], argv[3]);
        return once(line);
    }
    if (!strcmp(c, "put") && argc == 4) { /* The handheld's details too: one connection */
        nspire_handle_t *h;
        int r = open_handle(&h);
        if (r) return r;
        r = do_info(h);
        if (!r) r = do_put(h, argv[2], argv[3]);
        nspire_free(h);
        return r;
    }
    return usage();
}
